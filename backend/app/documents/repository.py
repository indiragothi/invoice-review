"""All SQLite access for documents. No HTTP, no providers, no policy."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.documents.models import Document, DocumentStatus
from app.validation.duplicates import InvoiceKey, ReceiptKey, key_from_json

# A rejected or failed record must not block a corrected re-issue of the same bill.
_IGNORED_FOR_DUPLICATES = (DocumentStatus.REJECTED, DocumentStatus.FAILED)


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **fields: Any) -> Document:
        document = Document(**fields)
        self.session.add(document)
        self.session.commit()
        return document

    def get(self, document_id: str) -> Document | None:
        return self.session.get(Document, document_id)

    def list(self, status: str | None = None, client_id: str | None = None) -> Sequence[Document]:
        query = select(Document).order_by(Document.created_at.desc(), Document.id)
        if status:
            query = query.where(Document.status == status)
        if client_id:
            query = query.where(Document.client_id == client_id)
        return self.session.scalars(query).all()

    def update(self, document: Document, **fields: Any) -> Document:
        for name, value in fields.items():
            setattr(document, name, value)
        self.session.commit()
        return document

    def delete(self, document: Document) -> None:
        self.session.delete(document)
        self.session.commit()

    def known_files(self, exclude_id: str | None = None) -> dict[str, str]:
        """`{sha256: document id}` of the other uploads, for the DUPLICATE_FILE warning."""
        query = select(Document.sha256, Document.id).order_by(Document.created_at, Document.id)
        if exclude_id:
            query = query.where(Document.id != exclude_id)
        found: dict[str, str] = {}
        for sha256, document_id in self.session.execute(query):
            found.setdefault(sha256, document_id)  # keep the earliest upload
        return found

    def existing_keys(
        self, client_id: str, document_type: str, exclude_id: str | None = None
    ) -> dict[str, InvoiceKey | ReceiptKey]:
        """`{document id: key}` of this client's other documents of the same kind, for the
        duplicate rules. Leaves out the document itself and rejected / failed records."""
        query = select(Document).where(
            Document.client_id == client_id,
            Document.document_type == document_type,
            Document.duplicate_key.is_not(None),
            Document.status.not_in(_IGNORED_FOR_DUPLICATES),
        )
        if exclude_id:
            query = query.where(Document.id != exclude_id)
        return {
            row.id: key_from_json(document_type, row.duplicate_key)
            for row in self.session.scalars(query)
            if row.duplicate_key
        }
