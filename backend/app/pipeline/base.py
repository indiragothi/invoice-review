"""The pipeline skeleton: a context that carries state, ordered steps, and a run trace.

Steps only transform the context. They decide no policy: rules live in `validation/`.
"""

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Protocol

from PIL import Image

from app.clients import Client
from app.config import Settings
from app.pipeline.agreement import Agreement
from app.providers import (
    CallInfo,
    ExtractionResult,
    LedgerResult,
    ProviderError,
    SecondReadingResult,
)
from app.reader.cache import ReadingCache, sha256_hex
from app.reader.schemas import ReadDocument
from app.schemas.documents import Invoice, Receipt
from app.schemas.extraction import Extraction
from app.schemas.fields import GroundedField
from app.schemas.ledger import LedgerSuggestion
from app.schemas.second_reading import SecondReading
from app.validation.duplicates import InvoiceKey, ReceiptKey
from app.validation.review import ReviewResult

PipelineStatus = Literal["ready", "needs_review", "failed"]

Extractor = Callable[[ReadDocument], ExtractionResult]
SecondReader = Callable[[Sequence[Image.Image], str], SecondReadingResult]  # (images, type)
ExistingKeys = Callable[[str], Mapping[str, InvoiceKey] | Mapping[str, ReceiptKey]]
LedgerSuggester = Callable[[Invoice | Receipt, str], LedgerResult]  # (document, client name)


class PipelineError(Exception):
    """A step cannot continue; the document becomes `failed` with this message."""


@dataclass
class StepTrace:
    step: str
    ms: int


@dataclass
class PipelineContext:
    data: bytes  # the uploaded file
    client: Client
    settings: Settings
    extractor: Extractor
    ledger_suggester: LedgerSuggester
    second_reader: SecondReader
    today: date = field(default_factory=date.today)
    reading_cache: ReadingCache | None = None
    known_files: Mapping[str, str] = field(default_factory=dict)  # {sha256: document id}
    # document type -> {document id: key} of this client's other documents (the repository).
    existing_keys: ExistingKeys = lambda _document_type: {}

    sha256: str = field(init=False)
    cache_hit: bool = False
    reading: ReadDocument | None = None
    images: list[Image.Image] = field(default_factory=list)
    extraction: Extraction | None = None
    call: CallInfo | None = None
    document: Invoice | Receipt | None = None
    grounded: dict[str, GroundedField] = field(default_factory=dict)
    review: ReviewResult | None = None
    second_reading: SecondReading | None = None
    second_call: CallInfo | None = None
    # per field: agree | differ | missing | filled (empty when the second reading did not run)
    agreement: dict[str, Agreement] = field(default_factory=dict)
    second_note: dict[str, object] = field(default_factory=dict)  # ran? why not?
    ledger: LedgerSuggestion | None = None
    ledger_call: CallInfo | None = None
    trace: list[StepTrace] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.sha256 = sha256_hex(self.data)

    @property
    def status(self) -> PipelineStatus:
        return self.review.status if self.review else "failed"


class Step(Protocol):
    name: str

    def __call__(self, context: PipelineContext) -> None: ...


def run_pipeline(
    steps: Sequence[Step], context: PipelineContext
) -> tuple[PipelineContext, PipelineError | ProviderError | None]:
    """Run the steps in order. Returns the context and the error that stopped it (None on
    success): `PipelineError` = the file cannot be used, `ProviderError` = the model call failed."""
    for step in steps:
        started = time.perf_counter()
        try:
            step(context)
        except (PipelineError, ProviderError) as error:
            return context, error
        finally:
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            context.trace.append(StepTrace(step.name, elapsed_ms))
    return context, None
