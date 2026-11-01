"""HTTP routes for documents: parsing, response models and status codes only.

Everything else (workflow, state, rules) is in `DocumentService`.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from app.config import APP_CONFIG
from app.correction_email.schemas import CorrectionEmailResponse
from app.documents.intake import IntakeError
from app.documents.models import Document, DocumentStatus
from app.documents.projection import InvalidValueError, UnknownFieldError
from app.documents.repository import DocumentRepository
from app.documents.schemas import (
    BulkApproveRequest,
    BulkApproveResponse,
    DecisionRequest,
    DocumentResponse,
    EditRequest,
    LedgerSelection,
)
from app.documents.service import (
    ClientNotFoundError,
    ConflictError,
    DocumentNotFoundError,
    DocumentService,
    LedgerNotFoundError,
    PageNotFoundError,
)
from app.providers import ProviderError

router = APIRouter(prefix="/api/documents", tags=["documents"])


def get_service(request: Request) -> Iterator[DocumentService]:
    """One database session and one service per request."""
    state = request.app.state
    with state.session_factory() as session:
        yield DocumentService(
            DocumentRepository(session),
            state.settings,
            state.extractor,
            state.ledger_suggester,
            reading_cache=state.reading_cache,
            email_drafter=state.email_drafter,
            data_dir=state.data_dir,
        )


ServiceDep = Annotated[DocumentService, Depends(get_service)]


def _body(document: Document) -> dict:
    return DocumentResponse.model_validate(document).model_dump(mode="json")


def _processed(document: Document, success_status: int) -> JSONResponse:
    """A document that went through the pipeline. A failed one is still saved, so the answer
    carries it: 502 when the provider failed, 422 when the file is not an invoice or receipt."""
    if document.status == DocumentStatus.FAILED:
        provider_failed = (document.pipeline_run or {}).get("error_kind") == "provider"
        return JSONResponse(
            {"detail": document.error_message, "document": _body(document)},
            status_code=502 if provider_failed else 422,
        )
    return JSONResponse(_body(document), status_code=success_status)


def _not_found(error: Exception) -> HTTPException:
    return HTTPException(404, f"Not found: {error}")


@router.post("", status_code=201, response_model=DocumentResponse)
def upload(
    service: ServiceDep, file: Annotated[UploadFile, File()], client_id: Annotated[str, Form()]
):
    # Read one byte past the limit: enough to know it is too large without loading a huge body.
    data = file.file.read(APP_CONFIG.max_upload_bytes + 1)
    try:
        document = service.upload(data, file.filename or "upload", client_id)
    except IntakeError as error:
        raise HTTPException(error.status_code, error.message) from error
    except ClientNotFoundError as error:
        raise HTTPException(404, f"Unknown client: {client_id}") from error
    return _processed(document, 201)


@router.post("/bulk-approve", response_model=BulkApproveResponse)
def bulk_approve(body: BulkApproveRequest, service: ServiceDep):
    approved, skipped = service.bulk_approve(body.ids)
    return {"approved": approved, "skipped": skipped}


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    service: ServiceDep, status: DocumentStatus | None = None, client_id: str | None = None
):
    return service.list_documents(status=status.value if status else None, client_id=client_id)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str, service: ServiceDep):
    try:
        return service.get(document_id)
    except DocumentNotFoundError as error:
        raise _not_found(error) from error


@router.get("/{document_id}/file")
def get_file(document_id: str, service: ServiceDep):
    try:
        document = service.get(document_id)
    except DocumentNotFoundError as error:
        raise _not_found(error) from error
    path = service.file_path(document)
    if not path.exists():
        raise HTTPException(404, "The stored file is missing.")
    return FileResponse(
        path,
        media_type=document.content_type,
        headers={"Content-Disposition": "inline", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/{document_id}/pages/{page}")
def get_page(document_id: str, page: int, service: ServiceDep):
    try:
        png = service.page_png(document_id, page)
    except (DocumentNotFoundError, PageNotFoundError) as error:
        raise _not_found(error) from error
    return Response(png, media_type="image/png", headers={"X-Content-Type-Options": "nosniff"})


@router.put("/{document_id}", response_model=DocumentResponse)
def edit(document_id: str, body: EditRequest, service: ServiceDep):
    try:
        return service.edit(document_id, body.fields)
    except DocumentNotFoundError as error:
        raise _not_found(error) from error
    except UnknownFieldError as error:
        raise HTTPException(422, f"Unknown field: {error}") from error
    except InvalidValueError as error:
        raise HTTPException(422, str(error)) from error
    except ConflictError as error:
        raise HTTPException(409, str(error)) from error


@router.put("/{document_id}/ledger", response_model=DocumentResponse)
def select_ledger(document_id: str, body: LedgerSelection, service: ServiceDep):
    try:
        return service.select_ledger(document_id, body.ledger_code)
    except DocumentNotFoundError as error:
        raise _not_found(error) from error
    except LedgerNotFoundError as error:
        raise HTTPException(404, f"Unknown ledger: {body.ledger_code}") from error
    except ConflictError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/{document_id}/decision", response_model=DocumentResponse)
def decide(document_id: str, body: DecisionRequest, service: ServiceDep):
    try:
        return service.decide(document_id, body.decision)
    except DocumentNotFoundError as error:
        raise _not_found(error) from error
    except ConflictError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/{document_id}/correction-email", response_model=CorrectionEmailResponse)
def correction_email(document_id: str, service: ServiceDep):
    try:
        result, issues = service.correction_email(document_id)
    except DocumentNotFoundError as error:
        raise _not_found(error) from error
    except ConflictError as error:
        raise HTTPException(409, str(error)) from error
    except ProviderError as error:
        raise HTTPException(502, str(error)) from error
    return CorrectionEmailResponse(
        subject=result.draft.subject,
        body=result.draft.body,
        issue_codes=[i.code.value for i in issues],
    )


@router.post("/{document_id}/retry", response_model=DocumentResponse)
def retry(document_id: str, service: ServiceDep):
    try:
        document = service.retry(document_id)
    except DocumentNotFoundError as error:
        raise _not_found(error) from error
    except ConflictError as error:
        raise HTTPException(409, str(error)) from error
    return _processed(document, 200)


@router.delete("/{document_id}", status_code=204)
def delete(document_id: str, service: ServiceDep):
    try:
        service.delete(document_id)
    except DocumentNotFoundError as error:
        raise _not_found(error) from error
