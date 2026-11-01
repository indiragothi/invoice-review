"""The `documents` table: one row per upload, as in docs/architecture.md section 7.

Stage columns keep the pipeline story visible; the editable review lives in `review_data`.
`document_type` and `duplicate_key` replace the three `norm_*` columns of the first design so
that receipts (merchant + date + total) are covered too (docs/decisions.md D14).
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DocumentStatus(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


def _now() -> datetime:
    return datetime.now(UTC)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id: Mapped[str] = mapped_column(String(16), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(64))  # <uuid>.<ext>
    content_type: Mapped[str] = mapped_column(String(32))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default=DocumentStatus.PROCESSING, index=True)

    document_type: Mapped[str | None] = mapped_column(String(16))  # invoice | receipt
    duplicate_key: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # duplicates.key_to_json

    reading: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    classification: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    document_review: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    review_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    issues: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    ledger: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    pipeline_run: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
