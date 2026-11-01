"""Pipeline steps: reading, extraction, grounding, validation, ledger suggestion.

Still to come in M3: document review (second reading + merge).
"""

from app.accounting.catalog import checked_ledger_code
from app.normalisation.assemble import normalise_extraction
from app.pipeline.base import PipelineContext, PipelineError, Step
from app.pipeline.grounding import ground_extraction
from app.providers import ProviderError
from app.reader import UnsupportedFileError, read_document, render_images
from app.schemas.ledger import LedgerSuggestion
from app.validation.duplicates import duplicate_file_issue
from app.validation.review import review_document


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
    return [ReadingStep(), ExtractionStep(), GroundingStep(), ValidationStep(), LedgerStep()]
