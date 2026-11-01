"""HTTP response shapes for documents (docs/api-and-pipeline.md, DocumentResponse)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.issues import ValidationIssue


class LedgerState(BaseModel):
    suggested_code: str | None
    reason: str
    selected_code: str | None = None
    overridden: bool = False


class DocumentResponse(BaseModel):
    """One review. The big stage columns (`reading`, `extraction`) are not sent."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    client_id: str
    original_filename: str
    content_type: str
    page_count: int
    status: str
    document_type: str | None
    classification: dict[str, Any] | None
    review_data: dict[str, Any] | None
    document_review: dict[str, Any] | None
    issues: list[ValidationIssue]
    ledger: LedgerState | None
    history: list[dict[str, Any]]
    pipeline_run: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    @field_validator("issues", "history", mode="before")
    @classmethod
    def _none_is_empty(cls, value: object) -> object:
        """A failed document has no issues yet (the column is empty): send an empty list."""
        return [] if value is None else value
