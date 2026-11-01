"""Document workflow: intake -> store the file -> run the pipeline -> save the result.

The service owns state transitions; the repository only reads and writes rows, and the pipeline
only transforms a context. A document is always saved, even when the pipeline fails, so the
reviewer can see why and retry.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.clients import CLIENTS_BY_ID
from app.config import Settings
from app.documents.intake import check_upload, new_stored_filename, save_upload, uploads_dir
from app.documents.models import Document, DocumentStatus
from app.documents.repository import DocumentRepository
from app.pipeline.base import Extractor, LedgerSuggester, PipelineContext, run_pipeline
from app.pipeline.steps import build_default_pipeline
from app.providers import ProviderError
from app.reader.cache import ReadingCache, sha256_hex
from app.validation.duplicates import invoice_key, key_to_json, receipt_key


class ClientNotFoundError(Exception):
    pass


class DocumentNotFoundError(Exception):
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
        reading_cache: ReadingCache | None = None,
        data_dir: Path | None = None,
        today: Callable[[], date] = date.today,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.extractor = extractor
        self.ledger_suggester = ledger_suggester
        self.reading_cache = reading_cache
        self.data_dir = data_dir
        self.today = today

    # ------------------------------------------------------------------ queries

    def get(self, document_id: str) -> Document:
        document = self.repository.get(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        return document

    def list(self, status: str | None = None, client_id: str | None = None):
        return self.repository.list(status=status, client_id=client_id)

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
        path = uploads_dir(self.data_dir) / document.stored_filename
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
            today=self.today(),
            reading_cache=self.reading_cache,
            known_files=repository.known_files(exclude_id=document.id),
            existing_keys=lambda kind: repository.existing_keys(
                document.client_id, kind, exclude_id=document.id
            ),
        )
        context, error = run_pipeline(build_default_pipeline(), context)

        calls = [c for c in (context.call, context.ledger_call) if c is not None]
        pipeline_run: dict[str, Any] = {
            "provider": self.settings.llm_provider,
            "model": self.settings.active_model,
            "prompt_versions": {
                "extraction": context.call.prompt_version if context.call else None,
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
