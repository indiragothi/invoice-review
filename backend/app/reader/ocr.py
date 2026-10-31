"""Words from an image with RapidOCR.

RapidOCR returns text lines, and with `return_word_box=True` also one box and one confidence per
character. Spaces are not returned, so characters are grouped into words wherever the horizontal
gap is wider than a normal letter gap. A word's confidence is its weakest character: a single
doubtful "O" in a GSTIN must make the whole GSTIN doubtful.
"""

from functools import lru_cache
from statistics import median
from typing import Any

from PIL import Image
from rapidocr_onnxruntime import RapidOCR

from app.reader.render import to_png_bytes
from app.reader.schemas import Box, RawWord

WORD_GAP_RATIO = 0.45  # gap wider than this share of a median character width starts a new word


@lru_cache
def _engine() -> RapidOCR:
    return RapidOCR()


def _bounds(points: list[list[float]]) -> Box:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _union(boxes: list[Box]) -> Box:
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _split_line(line_index: int, entry: list[Any]) -> list[RawWord]:
    line_box, text, score = _bounds(entry[0]), str(entry[1]), float(entry[2])
    char_boxes = entry[3] if len(entry) > 5 else None
    chars = entry[4] if len(entry) > 5 else None
    char_scores = entry[5] if len(entry) > 5 else None

    if not chars or "".join(chars) != text.replace(" ", ""):
        return [RawWord(text, line_box, score, line_index)]  # no usable character detail

    boxes = [_bounds(b) for b in char_boxes]
    widths = [b[2] - b[0] for b in boxes]
    gap_limit = WORD_GAP_RATIO * median(widths)

    words: list[RawWord] = []
    start = 0
    for i in range(1, len(chars) + 1):
        at_end = i == len(chars)
        if not at_end and boxes[i][0] - boxes[i - 1][2] <= gap_limit:
            continue
        words.append(
            RawWord(
                text="".join(chars[start:i]),
                box=_union(boxes[start:i]),
                confidence=min(float(s) for s in char_scores[start:i]),
                line_key=line_index,
            )
        )
        start = i
    return words


def words_from_image(image: Image.Image) -> list[RawWord]:
    result, _ = _engine()(to_png_bytes(image), return_word_box=True)
    words: list[RawWord] = []
    for line_index, entry in enumerate(result or []):
        words.extend(_split_line(line_index, entry))
    return words
