import io

import pymupdf
import pytest
from PIL import Image

from app.config import APP_CONFIG
from app.documents.intake import (
    IntakeError,
    check_upload,
    new_stored_filename,
    save_upload,
    uploads_dir,
)


def pdf_bytes(pages: int) -> bytes:
    pdf = pymupdf.open()
    for number in range(pages):
        pdf.new_page().insert_text((72, 72), f"page {number + 1}")
    data = pdf.tobytes()
    pdf.close()
    return data


def image_bytes(fmt: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(buffer, format=fmt)
    return buffer.getvalue()


def rejected(data: bytes) -> IntakeError:
    with pytest.raises(IntakeError) as caught:
        check_upload(data)
    return caught.value


def test_accepts_pdf_png_and_jpeg_and_counts_pages():
    pdf = check_upload(pdf_bytes(2))
    assert (pdf.content_type, pdf.extension, pdf.page_count) == ("application/pdf", "pdf", 2)
    png = check_upload(image_bytes("PNG"))
    assert (png.content_type, png.extension, png.page_count) == ("image/png", "png", 1)
    jpeg = check_upload(image_bytes("JPEG"))
    assert (jpeg.content_type, jpeg.extension) == ("image/jpeg", "jpg")


def test_five_pages_pass_and_six_are_413():
    assert check_upload(pdf_bytes(APP_CONFIG.max_pages)).page_count == APP_CONFIG.max_pages
    assert rejected(pdf_bytes(APP_CONFIG.max_pages + 1)).status_code == 413


def test_a_program_renamed_to_pdf_is_415_because_only_the_bytes_count():
    assert rejected(b"MZ\x90\x00 this is an exe").status_code == 415
    assert rejected(b"").status_code == 415


def test_an_oversize_file_is_413_before_anything_is_opened():
    assert rejected(b"%PDF-" + b"0" * APP_CONFIG.max_upload_bytes).status_code == 413


def test_a_damaged_pdf_is_415():
    assert rejected(b"%PDF-1.7 this is not a real pdf").status_code == 415


def test_stored_names_are_generated_and_the_file_lands_in_uploads(tmp_path):
    first, second = new_stored_filename("pdf"), new_stored_filename("pdf")
    assert first != second and first.endswith(".pdf") and len(first) == 40
    path = save_upload(b"data", first, base=tmp_path)
    assert path == uploads_dir(tmp_path) / first
    assert path.read_bytes() == b"data"
