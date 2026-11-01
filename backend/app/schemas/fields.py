"""Provenance of one extracted value after code has checked it.

The LLM only says *which words* hold a value. Code verifies that claim (grounding), builds the
box from the real word boxes and computes confidence. A model's own confidence is never stored.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.reader.schemas import Box

# grounded: value found in the cited words. ungrounded: cited words do not contain it.
# missing: nothing printed / nothing extracted (value is null).
Grounding = Literal["grounded", "ungrounded", "missing"]

# human: the reviewer typed or accepted the value (confidence 1.0).
FieldSource = Literal["pdf_text", "ocr", "reading_b", "human"]


class GroundedField(BaseModel):
    raw: str | None = Field(description="Value exactly as the model copied it from the document.")
    evidence: list[str] = Field(
        default_factory=list, description="Cited word IDs, after any re-pointing."
    )
    page: int | None = None
    box: Box | None = Field(
        default=None, description="Union of the evidence word boxes, built by code."
    )
    grounding: Grounding = "missing"
    source: FieldSource = "pdf_text"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
