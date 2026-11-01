"""`GET /api/export`: approved records as CSV or XLSX. Parsing and status codes only."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response

from app.documents.routes import ServiceDep
from app.documents.service import ClientNotFoundError
from app.export.files import CSV_MEDIA_TYPE, XLSX_MEDIA_TYPE, to_csv, to_xlsx

router = APIRouter(prefix="/api", tags=["export"])


@router.get("/export")
def export(
    service: ServiceDep,
    file_format: Annotated[Literal["csv", "xlsx"], Query(alias="format")] = "csv",
    client_id: str | None = None,
):
    try:
        rows = service.export_rows(client_id)
    except ClientNotFoundError as error:
        raise HTTPException(404, f"Unknown client: {client_id}") from error
    if file_format == "xlsx":
        content, media_type = to_xlsx(rows), XLSX_MEDIA_TYPE
    else:
        content, media_type = to_csv(rows), CSV_MEDIA_TYPE
    name = f"approved-{date.today().isoformat()}.{file_format}"
    return Response(
        content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
