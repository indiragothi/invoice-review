"""Upload intake: decide whether a file may enter the pipeline, and keep it under a safe name.

Checks (docs/security.md): the type comes from the first bytes, never from the file name; at most
5 MB; at most 5 pages. The stored name is generated (`<uuid>.<ext>`); the user's file name is only
kept as a label. Each rejection carries the HTTP status the route will return.
"""

import uuid
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.config import APP_CONFIG
from app.reader.render import sniff_content_type
from app.reader.schemas import ContentType

EXTENSIONS: dict[ContentType, str] = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpg",
}


class IntakeError(Exception):
    """The file is rejected. `status_code` is the HTTP status for the response."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class AcceptedUpload:
    content_type: ContentType
    extension: str
    page_count: int


def check_upload(data: bytes) -> AcceptedUpload:
    if len(data) > APP_CONFIG.max_upload_bytes:
        limit_mb = APP_CONFIG.max_upload_bytes // (1024 * 1024)
        raise IntakeError(413, f"The file is larger than {limit_mb} MB.")
    content_type = sniff_content_type(data)
    if content_type is None:
        raise IntakeError(415, "Only PDF, PNG and JPEG files are supported.")
    pages = _count_pages(data) if content_type == "application/pdf" else 1
    if pages > APP_CONFIG.max_pages:
        raise IntakeError(413, f"The file has {pages} pages; at most {APP_CONFIG.max_pages}.")
    return AcceptedUpload(content_type, EXTENSIONS[content_type], pages)


def _count_pages(data: bytes) -> int:
    try:
        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            if pdf.needs_pass:
                raise IntakeError(415, "Password-protected PDFs are not supported.")
            return pdf.page_count
    except IntakeError:
        raise
    except Exception as error:  # damaged file: PyMuPDF raises several exception types
        raise IntakeError(415, "This PDF could not be opened.") from error


def new_stored_filename(extension: str) -> str:
    return f"{uuid.uuid4()}.{extension}"


def uploads_dir(base: Path | None = None) -> Path:
    return (base or APP_CONFIG.data_dir) / "uploads"


def save_upload(data: bytes, stored_filename: str, base: Path | None = None) -> Path:
    """Write the bytes under the generated name. The name is never taken from user input."""
    directory = uploads_dir(base)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / stored_filename
    path.write_bytes(data)
    return path
