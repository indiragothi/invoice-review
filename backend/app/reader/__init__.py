"""Turn an uploaded file into page images and positioned, numbered words.

Digital PDF pages use their text layer; scans, photos and image-only PDF pages use OCR. Boxes are
in the pixels of the returned page images.
"""

from dataclasses import dataclass

import pymupdf
from PIL import Image

from app.reader.ocr import words_from_image
from app.reader.pdf_text import words_from_text_layer
from app.reader.render import load_image, render_pdf_page, sniff_content_type
from app.reader.schemas import ContentType, Page, RawWord, ReadDocument, TextSource, Word

__all__ = ["ReadResult", "UnsupportedFileError", "read_document", "sniff_content_type"]


class UnsupportedFileError(ValueError):
    pass


@dataclass
class ReadResult:
    document: ReadDocument
    images: list[Image.Image]  # one per page, index 0 = page 1


def _read_pdf(data: bytes) -> list[tuple[Image.Image, list[RawWord], TextSource]]:
    pages = []
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        for page in pdf:
            image = render_pdf_page(page)
            words = words_from_text_layer(page)
            if words is None:
                pages.append((image, words_from_image(image), "ocr"))
            else:
                pages.append((image, words, "pdf_text"))
    return pages


def read_document(data: bytes) -> ReadResult:
    content_type: ContentType | None = sniff_content_type(data)
    if content_type is None:
        raise UnsupportedFileError("Only PDF, PNG and JPEG files are supported.")

    if content_type == "application/pdf":
        raw_pages = _read_pdf(data)
    else:
        image = load_image(data)
        raw_pages = [(image, words_from_image(image), "ocr")]

    pages: list[Page] = []
    words: list[Word] = []
    images: list[Image.Image] = []
    line_numbers: dict[tuple[int, object], int] = {}
    for page_number, (image, raw_words, source) in enumerate(raw_pages, start=1):
        images.append(image)
        pages.append(
            Page(number=page_number, width=image.width, height=image.height, text_source=source)
        )
        for raw in raw_words:
            key = (page_number, raw.line_key)
            line = line_numbers.setdefault(key, len(line_numbers) + 1)
            x0, y0, x1, y1 = raw.box
            words.append(
                Word(
                    id=f"w{len(words) + 1}",
                    page=page_number,
                    line=line,
                    text=raw.text,
                    box=(round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)),
                    confidence=round(raw.confidence, 3),
                )
            )

    return ReadResult(
        document=ReadDocument(content_type=content_type, pages=pages, words=words), images=images
    )
