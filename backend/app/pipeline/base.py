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
from app.providers import CallInfo, ExtractionResult
from app.reader.cache import ReadingCache, sha256_hex
from app.reader.schemas import ReadDocument
from app.schemas.documents import Invoice, Receipt
from app.schemas.extraction import Extraction
from app.schemas.fields import GroundedField
from app.validation.review import ReviewResult

PipelineStatus = Literal["ready", "needs_review", "failed"]

Extractor = Callable[[ReadDocument], ExtractionResult]


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
    today: date = field(default_factory=date.today)
    reading_cache: ReadingCache | None = None
    known_files: Mapping[str, str] = field(default_factory=dict)  # {sha256: document id}

    sha256: str = field(init=False)
    cache_hit: bool = False
    reading: ReadDocument | None = None
    images: list[Image.Image] = field(default_factory=list)
    extraction: Extraction | None = None
    call: CallInfo | None = None
    document: Invoice | Receipt | None = None
    grounded: dict[str, GroundedField] = field(default_factory=dict)
    review: ReviewResult | None = None
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
) -> tuple[PipelineContext, str | None]:
    """Run the steps in order. Returns the context and an error message (None on success)."""
    for step in steps:
        started = time.perf_counter()
        try:
            step(context)
        except PipelineError as error:
            return context, str(error)
        finally:
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            context.trace.append(StepTrace(step.name, elapsed_ms))
    return context, None
