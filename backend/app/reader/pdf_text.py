"""Words from a PDF's own text layer: exact text and position, so confidence is 1.0."""

import pymupdf

from app.reader.render import RENDER_DPI
from app.reader.schemas import RawWord

MIN_TEXT_LAYER_WORDS = 5


def words_from_text_layer(page: pymupdf.Page) -> list[RawWord] | None:
    """Return the page's words, or None when the page has no usable text layer (a scan)."""
    entries = page.get_text("words", sort=True)
    if len(entries) < MIN_TEXT_LAYER_WORDS:
        return None
    scale = RENDER_DPI / 72
    words = []
    for x0, y0, x1, y1, text, block, line, _ in entries:
        if not text.strip():
            continue
        words.append(
            RawWord(
                text=text,
                box=(x0 * scale, y0 * scale, x1 * scale, y1 * scale),
                confidence=1.0,
                line_key=(block, line),
            )
        )
    return words
