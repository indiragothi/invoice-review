"""Document workflow: intake -> store the file -> run the pipeline -> save the result.

The service owns state transitions; the repository only reads and writes rows, and the pipeline
only transforms a context. A document is always saved, even when the pipeline fails, so the
reviewer can see why and retry.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.accounting.catalog import checked_ledger_code
from app.clients import CLIENTS_BY_ID, Client
from app.config import Settings
from app.correction_email.eligibility import eligible_issues
from app.documents.intake import check_upload, new_stored_filename, save_upload, uploads_dir
from app.documents.models import Document, DocumentStatus
from app.documents.projection import (
    agreement_of,
    apply_edits,
    build_review_data,
    extraction_with_values,
    grounded_fields,
    refresh_review_data,
)
from app.documents.repository import DocumentRepository
from app.export.rows import Cell, ExportFacts, build_row
from app.normalisation.assemble import normalise_extraction
from app.pipeline.base import (
    Extractor,
    LedgerSuggester,
    PipelineContext,
    SecondReader,
    run_pipeline,
)
from app.pipeline.steps import build_default_pipeline
from app.providers import EmailResult, ProviderError
from app.reader import render_images
from app.reader.cache import ReadingCache, sha256_hex
from app.reader.render import to_png_bytes
from app.schemas.documents import Invoice, Receipt
from app.schemas.extraction import Extraction
from app.schemas.issues import ValidationIssue
from app.validation.approval import DECIDED, approval_blockers, rejection_blockers
from app.validation.duplicates import duplicate_file_issue, invoice_key, key_to_json, receipt_key
from app.validation.review import review_document

EmailDrafter = Callable[[Invoice | Receipt, Client, list[ValidationIssue]], EmailResult]


class ClientNotFoundError(Exception):
    pass


class DocumentNotFoundError(Exception):
    pass


class PageNotFoundError(Exception):
    pass


class LedgerNotFoundError(Exception):
    pass


class ConflictError(Exception):
    """The action is not allowed in the document's current state (HTTP 409)."""


def _event(name: str, **details: Any) -> dict[str, Any]:
    return {"at": datetime.now(UTC).isoformat(), "event": name, **details}


class DocumentService:
    def __init__(
        self,
        repository: DocumentRepository,
        settings: Settings,
        extractor: Extractor,
        ledger_suggester: LedgerSuggester,
        second_reader: SecondReader,
        reading_cache: ReadingCache | None = None,
        email_drafter: EmailDrafter | None = None,
        data_dir: Path | None = None,
        today: Callable[[], date] = date.today,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.extractor = extractor
        self.ledger_suggester = ledger_suggester
        self.second_reader = second_reader
        self.reading_cache = reading_cache
        self.email_drafter = email_drafter
        self.data_dir = data_dir
        self.today = today

    # ------------------------------------------------------------------ queries

    def get(self, document_id: str) -> Document:
        document = self.repository.get(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        return document

    def list_documents(self, status: str | None = None, client_id: str | None = None):
        return self.repository.list(status=status, client_id=client_id)

    def file_path(self, document: Document) -> Path:
        """Where the original bytes are kept (the name is the generated one)."""
        return uploads_dir(self.data_dir) / document.stored_filename

    def page_png(self, document_id: str, page: int) -> bytes:
        """One page rendered as PNG, in the same pixels as the word boxes."""
        document = self.get(document_id)
        if not 1 <= page <= document.page_count:
            raise PageNotFoundError(page)
        path = self.file_path(document)
        if not path.exists():
            raise PageNotFoundError(page)
        return to_png_bytes(render_images(path.read_bytes())[page - 1])

    def delete(self, document_id: str) -> None:
        """Remove the review and its stored file (demo reset)."""
        document = self.get(document_id)
        self.file_path(document).unlink(missing_ok=True)
        self.repository.delete(document)

    # ------------------------------------------------------------------ human decisions

    def select_ledger(self, document_id: str, ledger_code: str) -> Document:
        """The reviewer confirms the suggestion or overrides it. Only catalog codes are allowed."""
        code = checked_ledger_code(ledger_code)
        if code is None:
            raise LedgerNotFoundError(ledger_code)
        document = self.get(document_id)
        if document.status in DECIDED:
            raise ConflictError(f"The record is already {document.status} and locked.")
        if document.ledger is None:
            raise ConflictError("This document has no ledger step yet; it is not processed.")
        suggested = document.ledger.get("suggested_code")
        ledger = {**document.ledger, "selected_code": code, "overridden": code != suggested}
        history = [
            *document.history,
            _event("ledger_selected", code=code, overridden=ledger["overridden"]),
        ]
        return self.repository.update(document, ledger=ledger, history=history)

    def decide(self, document_id: str, decision: str) -> Document:
        """Approve or reject. The approval invariant is enforced here, whatever route calls it."""
        document = self.get(document_id)
        blockers = self._blockers(document, decision)
        if blockers:
            raise ConflictError(" ".join(blockers))
        history = [*document.history, _event("decision", decision=decision)]
        return self.repository.update(document, status=DocumentStatus(decision), history=history)

    def bulk_approve(self, ids: list[str]) -> tuple[list[Document], list[dict[str, str]]]:
        """Approve what can be approved; return the rest with the reason. Same check as `decide`."""
        approved: list[Document] = []
        skipped: list[dict[str, str]] = []
        for document_id in dict.fromkeys(ids):  # in order, each id once
            document = self.repository.get(document_id)
            if document is None:
                skipped.append({"id": document_id, "reason": "Document not found."})
                continue
            blockers = self._blockers(document, "approved")
            if blockers:
                skipped.append({"id": document_id, "reason": " ".join(blockers)})
                continue
            history = [*document.history, _event("decision", decision="approved", bulk=True)]
            approved.append(
                self.repository.update(document, status=DocumentStatus.APPROVED, history=history)
            )
        return approved, skipped

    @staticmethod
    def _blockers(document: Document, decision: str) -> list[str]:
        if decision == "rejected":
            return rejection_blockers(document.status)
        issues = [ValidationIssue.model_validate(i) for i in document.issues or []]
        selected = (document.ledger or {}).get("selected_code")
        return approval_blockers(document.status, issues, selected)

    # ------------------------------------------------------------------ export

    def export_rows(self, client_id: str | None = None) -> list[dict[str, Cell]]:
        """One row per **approved** document (oldest first), from the current normalised fields.
        Nothing that is not approved is ever exported."""
        if client_id is not None and client_id not in CLIENTS_BY_ID:
            raise ClientNotFoundError(client_id)
        approved = self.repository.list(status=DocumentStatus.APPROVED.value, client_id=client_id)
        rows = []
        for document in reversed(approved):  # the repository lists newest first
            decisions = [h for h in document.history if h.get("event") == "decision"]
            facts = ExportFacts(
                document_id=document.id,
                client=CLIENTS_BY_ID[document.client_id],
                original_filename=document.original_filename,
                ledger=document.ledger,
                issues=[ValidationIssue.model_validate(i) for i in document.issues or []],
                approved_at=decisions[-1]["at"] if decisions else None,
            )
            rows.append(build_row(self._parsed(document), facts))
        return rows

    @staticmethod
    def _agreement(document: Document, review_data: dict[str, Any]) -> dict[str, Any]:
        """The second-reading result still in force: per field (not for an edited field, which is
        the human's value) plus the table-level differences, which no single edit can resolve."""
        stored = (document.document_review or {}).get("agreement", {})
        tables = {key: stored[key] for key in ("line_items", "tax_lines") if key in stored}
        return {**agreement_of(review_data), **tables}

    @staticmethod
    def _parsed(document: Document) -> Invoice | Receipt:
        """The normalised document as it is now: the stored extraction with the review values."""
        assert document.extraction is not None and document.review_data is not None
        extraction = extraction_with_values(
            Extraction.model_validate(document.extraction), document.review_data
        )
        parsed = normalise_extraction(extraction)
        assert parsed is not None  # the type was checked when the document was processed
        return parsed

    # ------------------------------------------------------------------ correction email

    def correction_email(self, document_id: str) -> tuple[EmailResult, list[ValidationIssue]]:
        """Draft (never send) an email asking the supplier to fix what only the supplier can.

        The issues come from the fixed eligibility list, not from the model, and the draft is
        built from the current (possibly edited) normalised fields, never from the file.
        `ProviderError` passes through when the model call fails.
        """
        document = self.get(document_id)
        if document.status in ("processing", "failed"):
            raise ConflictError(f"A {document.status} document has nothing to write about.")
        if document.review_data is None or document.extraction is None:
            raise ConflictError("This document has nothing to write about; upload it again.")
        if self.email_drafter is None:
            raise RuntimeError("No email drafter is configured.")
        issues = eligible_issues([ValidationIssue.model_validate(i) for i in document.issues or []])
        if not issues:
            raise ConflictError("There are no issues the supplier can fix.")
        parsed = self._parsed(document)
        result = self.email_drafter(parsed, CLIENTS_BY_ID[document.client_id], issues)
        codes = [i.code.value for i in issues]
        history = [*document.history, _event("correction_email_drafted", codes=codes)]
        self.repository.update(document, history=history)
        return result, issues

    # ------------------------------------------------------------------ editing

    def edit(self, document_id: str, edits: dict[str, str | None]) -> Document:
        """Apply the reviewer's corrections and run every rule again.

        An edited field is the human's (source `human`, confidence 1.0). The status follows the
        new result: an edit can fix a `needs_review` document or break a `ready` one.
        Raises `UnknownFieldError` / `InvalidValueError` (nothing is changed) and `ConflictError`.
        """
        document = self.get(document_id)
        if document.status in DECIDED:
            raise ConflictError(f"The record is already {document.status} and locked.")
        if document.status not in ("ready", "needs_review"):
            raise ConflictError(f"A {document.status} document cannot be edited.")
        if document.review_data is None or document.extraction is None:
            raise ConflictError("This document has nothing to edit; upload it again.")

        review_data, changes = apply_edits(document.review_data, edits)
        if not changes:
            return document
        extraction = extraction_with_values(
            Extraction.model_validate(document.extraction), review_data
        )
        parsed = normalise_extraction(extraction)
        assert parsed is not None  # the type was checked when the document was processed
        repository = self.repository
        result = review_document(
            parsed,
            grounded_fields(review_data),
            CLIENTS_BY_ID[document.client_id],
            self.today(),
            existing=repository.existing_keys(
                document.client_id, parsed.document_type, exclude_id=document.id
            ),
            agreement=self._agreement(document, review_data),
        )
        issues = list(result.issues)
        if issue := duplicate_file_issue(
            document.sha256, repository.known_files(exclude_id=document.id)
        ):
            issues.append(issue)
        key = (invoice_key if parsed.document_type == "invoice" else receipt_key)(parsed)  # type: ignore[arg-type]
        history = [*document.history, _event("edited", changes=changes, status=result.status)]
        return repository.update(
            document,
            status=DocumentStatus(result.status),
            review_data=refresh_review_data(review_data, result.fields),
            issues=[i.model_dump(mode="json") for i in issues],
            duplicate_key=key_to_json(key) if key else None,
            history=history,
        )

    # ------------------------------------------------------------------ upload / retry

    def upload(self, data: bytes, filename: str, client_id: str) -> Document:
        """Accept a file for a client and run the pipeline. Raises `ClientNotFoundError` or
        `IntakeError` before anything is stored; after that a document always comes back."""
        if client_id not in CLIENTS_BY_ID:
            raise ClientNotFoundError(client_id)
        accepted = check_upload(data)
        stored = new_stored_filename(accepted.extension)
        save_upload(data, stored, self.data_dir)
        document = self.repository.create(
            client_id=client_id,
            original_filename=Path(filename).name[:255] or "upload",
            stored_filename=stored,
            content_type=accepted.content_type,
            sha256=sha256_hex(data),
            page_count=accepted.page_count,
            status=DocumentStatus.PROCESSING,
            history=[_event("uploaded")],
        )
        return self._process(document, data)

    def retry(self, document_id: str) -> Document:
        document = self.get(document_id)
        if document.status != DocumentStatus.FAILED:
            raise ConflictError("Only a failed document can be retried.")
        path = self.file_path(document)
        if not path.exists():
            raise ConflictError("The stored file is missing; upload it again.")
        history = [*document.history, _event("retry")]
        self.repository.update(
            document, status=DocumentStatus.PROCESSING, error_message=None, history=history
        )
        return self._process(document, path.read_bytes())

    # ------------------------------------------------------------------ the pipeline run

    def _process(self, document: Document, data: bytes) -> Document:
        repository = self.repository
        context = PipelineContext(
            data=data,
            client=CLIENTS_BY_ID[document.client_id],
            settings=self.settings,
            extractor=self.extractor,
            ledger_suggester=self.ledger_suggester,
            second_reader=self.second_reader,
            today=self.today(),
            reading_cache=self.reading_cache,
            known_files=repository.known_files(exclude_id=document.id),
            existing_keys=lambda kind: repository.existing_keys(
                document.client_id, kind, exclude_id=document.id
            ),
        )
        context, error = run_pipeline(build_default_pipeline(), context)

        calls = [
            c for c in (context.call, context.second_call, context.ledger_call) if c is not None
        ]
        pipeline_run: dict[str, Any] = {
            "provider": self.settings.llm_provider,
            "model": self.settings.active_model,
            "prompt_versions": {
                "extraction": context.call.prompt_version if context.call else None,
                "review": context.second_call.prompt_version if context.second_call else None,
                "ledger": context.ledger_call.prompt_version if context.ledger_call else None,
            },
            "calls": len(calls),
            "total_ms": sum(t.ms for t in context.trace),
            "steps": [{"step": t.step, "ms": t.ms} for t in context.trace],
            "reading_from_cache": context.cache_hit,
            "error_kind": None,
        }
        fields: dict[str, Any] = {
            "reading": context.reading.model_dump(mode="json") if context.reading else None,
            "extraction": (
                context.extraction.model_dump(mode="json") if context.extraction else None
            ),
            "classification": (
                {"document_type": context.extraction.document_type} if context.extraction else None
            ),
        }

        if error is not None:
            pipeline_run["error_kind"] = "provider" if isinstance(error, ProviderError) else "file"
            fields.update(
                status=DocumentStatus.FAILED,
                error_message=str(error)[:500],
                pipeline_run=pipeline_run,
            )
        else:
            assert context.document is not None and context.review and context.ledger
            key = (invoice_key if context.document.document_type == "invoice" else receipt_key)(
                context.document  # type: ignore[arg-type]
            )
            fields.update(
                status=DocumentStatus(context.status),
                document_type=context.document.document_type,
                duplicate_key=key_to_json(key) if key else None,
                issues=[i.model_dump(mode="json") for i in context.review.issues],
                review_data=build_review_data(context.review.fields, context.agreement),
                document_review={
                    "mode": self.settings.second_reading,
                    **context.second_note,
                    "agreement": context.agreement,
                    "reading_b": (
                        context.second_reading.model_dump(mode="json")
                        if context.second_reading
                        else None
                    ),
                },
                ledger={
                    "suggested_code": context.ledger.suggested_code,
                    "reason": context.ledger.reason,
                    "selected_code": None,
                    "overridden": False,
                },
                pipeline_run=pipeline_run,
                error_message=None,
            )
        fields["history"] = [*document.history, _event("processed", status=str(fields["status"]))]
        return repository.update(document, **fields)
