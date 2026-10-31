"""File type detection and page images.

Every page becomes one RGB image. Word boxes are expressed in that image's pixels, which is also
what the review screen displays, so a box can be drawn without any coordinate conversion.
"""

import io

import pymupdf
from PIL import Image, ImageOps

from app.reader.schemas import ContentType

RENDER_DPI = 150
MAX_IMAGE_SIDE = 2200


def sniff_content_type(data: bytes) -> ContentType | None:
    """Decide the type from the file's first bytes, never from its name."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def render_pdf_page(page: pymupdf.Page) -> Image.Image:
    pix = page.get_pixmap(dpi=RENDER_DPI, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def load_image(data: bytes) -> Image.Image:
    """Open a photo or scan upright (EXIF rotation applied) and cap its size."""
    with Image.open(io.BytesIO(data)) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    longest = max(image.size)
    if longest > MAX_IMAGE_SIDE:
        scale = MAX_IMAGE_SIDE / longest
        image = image.resize(
            (round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS
        )
    return image


def to_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
