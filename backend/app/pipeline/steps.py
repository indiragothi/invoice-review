"""The first four pipeline steps: reading, extraction, grounding, validation.

Still to come in M3: document review (second reading + merge) and ledger suggestion.
"""

from app.normalisation.assemble import normalise_extraction
from app.pipeline.base import PipelineContext, PipelineError, Step
from app.pipeline.grounding import ground_extraction
from app.reader import UnsupportedFileError, read_document
from app.validation.review import review_document


class ReadingStep:
    name = "reading"

    def __call__(self, context: PipelineContext) -> None:
        try:
            result = read_document(context.data)
        except UnsupportedFileError as error:
            raise PipelineError(str(error)) from error
        context.reading = result.document
        context.images = result.images
        if not result.document.words:
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
        context.review = review_document(
            context.document, context.grounded, context.client, context.today
        )


def build_default_pipeline() -> list[Step]:
    return [ReadingStep(), ExtractionStep(), GroundingStep(), ValidationStep()]
