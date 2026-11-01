"""Pipeline steps: reading, extraction, grounding, document review (second reading + merge),
validation, ledger suggestion.
"""

from app.accounting.catalog import checked_ledger_code
from app.config import APP_CONFIG
from app.normalisation.assemble import normalise_extraction
from app.pipeline.agreement import compare_and_fill, in_doubt
from app.pipeline.base import PipelineContext, PipelineError, Step
from app.pipeline.grounding import ground_extraction
from app.providers import ProviderError
from app.reader import UnsupportedFileError, read_document, render_images
from app.schemas.ledger import LedgerSuggestion
from app.validation.duplicates import duplicate_file_issue
from app.validation.review import required_fields, review_document


class ReadingStep:
    name = "reading"

    def __call__(self, context: PipelineContext) -> None:
        cache = context.reading_cache
        try:
            cached = cache.get(context.sha256) if cache else None
            if cached is not None:
                context.reading, context.images = cached, render_images(context.data)
                context.cache_hit = True
            else:
                result = read_document(context.data)
                context.reading, context.images = result.document, result.images
                if cache and result.document.words:
                    cache.put(context.sha256, result.document)
        except UnsupportedFileError as error:
            raise PipelineError(str(error)) from error
        if not context.reading.words:
            raise PipelineError("No readable text was found in this file.")


class ExtractionStep:
    name = "extraction"

    def __call__(self, context: PipelineContext) -> None:
        assert context.reading is not None
        result = context.extractor(context.reading)
        context.extraction = result.extraction
        context.call = result.call
        if result.extraction.document_type == "other":
            raise PipelineError("This does not look like an invoice or a receipt.")


class GroundingStep:
    name = "grounding"

    def __call__(self, context: PipelineContext) -> None:
        assert context.reading is not None and context.extraction is not None
        context.grounded = ground_extraction(context.extraction, context.reading)
        context.document = normalise_extraction(context.extraction)


class DocumentReviewStep:
    """The independent second reading from the page images, and the merge (docs/architecture.md).

    `SECOND_READING=never` skips it; `on_doubt` runs it only when a required field is missing,
    not found in the words or below the confidence threshold; `always` runs it every time.
    A gap in reading A is filled only from a value that is in the page words. If the call fails
    the document goes on without it: the second reading is a check, not a requirement."""

    name = "document_review"

    def __call__(self, context: PipelineContext) -> None:
        assert context.reading and context.extraction and context.document
        mode = context.settings.second_reading
        if mode == "never":
            context.second_note = {"ran": False, "why": "SECOND_READING=never"}
            return
        if mode == "on_doubt" and not in_doubt(
            context.grounded, required_fields(context.document), APP_CONFIG.confidence_threshold
        ):
            context.second_note = {"ran": False, "why": "no required field in doubt"}
            return
        try:
            result = context.second_reader(context.images, context.extraction.document_type)
        except ProviderError as error:
            context.second_note = {"ran": False, "why": "provider error", "error": str(error)}
            return
        merged, agreement = compare_and_fill(context.extraction, result.reading, context.reading)
        filled = [path for path, status in agreement.items() if status == "filled"]
        if filled:
            grounded = ground_extraction(merged, context.reading)
            for path in filled:
                grounded[path] = grounded[path].model_copy(update={"source": "reading_b"})
            context.grounded = grounded
            context.document = normalise_extraction(merged)
        context.second_reading, context.second_call = result.reading, result.call
        context.agreement = agreement
        context.second_note = {"ran": True, "why": mode, "filled": filled}


class ValidationStep:
    name = "validation"

    def __call__(self, context: PipelineContext) -> None:
        assert context.document is not None
        existing = context.existing_keys(context.document.document_type)
        review = review_document(
            context.document,
            context.grounded,
            context.client,
            context.today,
            existing=existing,
            agreement=context.agreement,
        )
        if issue := duplicate_file_issue(context.sha256, context.known_files):
            review.issues.append(issue)  # a warning: the status does not change
        context.review = review


class LedgerStep:
    name = "ledger_suggestion"

    def __call__(self, context: PipelineContext) -> None:
        assert context.document is not None
        try:
            result = context.ledger_suggester(context.document, context.client.name)
        except ProviderError as error:
            # The extraction is worth keeping: the reviewer can pick the ledger by hand.
            reason = "Ledger suggestion is unavailable ({}). Pick one by hand."
            reason = reason.format("provider busy" if error.busy else "provider error")
            context.ledger = LedgerSuggestion(suggested_code=None, reason=reason)
            return
        context.ledger_call = result.call
        code = checked_ledger_code(result.choice.code)
        reason = result.choice.reason.strip()
        if code is None:
            # The model named something outside the catalog: keep no code, the reviewer picks.
            reason = f"No valid ledger suggested (the model answered {result.choice.code!r})."
        context.ledger = LedgerSuggestion(suggested_code=code, reason=reason)


def build_default_pipeline() -> list[Step]:
    return [
        ReadingStep(),
        ExtractionStep(),
        GroundingStep(),
        DocumentReviewStep(),
        ValidationStep(),
        LedgerStep(),
    ]
