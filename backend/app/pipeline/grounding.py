"""Grounding: check that each value the model returned really appears in the words it cited.

The model only says which words hold a value. This module verifies the claim, re-points an
evidence list that is off by a word, builds the box from the real word boxes and computes the
base confidence. A value that cannot be found is `ungrounded` (confidence 0, no box). Pure code:
no I/O, no model calls.
"""

from collections.abc import Iterator

from app.reader.schemas import Box, ReadDocument, Word
from app.schemas.extraction import Evidenced, Extraction
from app.schemas.fields import GroundedField


def _squash(text: str) -> str:
    """Compare ignoring spaces and case, so OCR-lost spaces ("RestaurantPvtLtd") still match."""
    return "".join(text.split()).casefold()


def _union(words: list[Word]) -> Box:
    return (
        min(w.box[0] for w in words),
        min(w.box[1] for w in words),
        max(w.box[2] for w in words),
        max(w.box[3] for w in words),
    )


def _windows(words: list[Word], target: str, *, exact: bool) -> Iterator[list[Word]]:
    """Runs of consecutive words whose joined text contains (or equals) `target`, shortest first."""
    for size in range(1, len(words) + 1):
        for start in range(len(words) - size + 1):
            window = words[start : start + size]
            joined = _squash("".join(w.text for w in window))
            if joined == target if exact else target in joined:
                yield window


def _centre(words: list[Word]) -> tuple[float, float]:
    x0, y0, x1, y1 = _union(words)
    return (x0 + x1) / 2, (y0 + y1) / 2


NEIGHBOUR_WORDS = 2  # last-resort reach, in reading order, when the cited word is in the next row


def _neighbours(document: ReadDocument, cited: list[Word]) -> list[Word]:
    ids = {w.id for w in cited}
    keep: set[int] = set()
    for index, word in enumerate(document.words):
        if word.id in ids:
            keep.update(range(index - NEIGHBOUR_WORDS, index + NEIGHBOUR_WORDS + 1))
    return [w for i, w in enumerate(document.words) if i in keep]


def _same_row(document: ReadDocument, cited: list[Word]) -> list[Word]:
    """Words on the cited words' pages whose vertical centre falls inside a cited word's box.

    The reader's `line` number splits table cells onto separate lines, so a row is found by
    geometry, not by line number.
    """
    row = []
    for word in document.words:
        mid = (word.box[1] + word.box[3]) / 2
        if any(c.page == word.page and c.box[1] <= mid <= c.box[3] for c in cited):
            row.append(word)
    return sorted(row, key=lambda w: (w.page, w.box[0]))


def _confidence(words: list[Word], source: str) -> float:
    if source == "pdf_text":
        return 1.0
    return max(0.0, min(1.0, sum(w.confidence for w in words) / len(words)))


def ground_value(
    field: Evidenced, document: ReadDocument, *, by_id: dict[str, Word] | None = None
) -> GroundedField:
    if field.value is None or not field.value.strip():
        return GroundedField(raw=field.value, grounding="missing", confidence=0.0)

    by_id = by_id or {w.id: w for w in document.words}
    target = _squash(field.value)
    cited = sorted(
        (by_id[i] for i in dict.fromkeys(field.evidence) if i in by_id),
        key=lambda w: (w.page, w.line, w.box[0]),
    )

    found = next(_windows(cited, target, exact=False), None) if cited else None
    if found is None and cited:
        # The model cited a neighbouring word. Look along the same row; here only a whole-word
        # match counts, so "9" is never found inside "1,980". Take the match nearest the cited
        # words; if the row has nothing, try the words around them in reading order.
        cx, cy = _centre(cited)
        for pool in (_same_row(document, cited), _neighbours(document, cited)):
            found = min(
                _windows(pool, target, exact=True),
                key=lambda win: (abs(_centre(win)[0] - cx) + abs(_centre(win)[1] - cy), len(win)),
                default=None,
            )
            if found is not None:
                break

    if found is None:
        return GroundedField(
            raw=field.value, evidence=list(field.evidence), grounding="ungrounded", confidence=0.0
        )

    page = found[0].page
    found = [w for w in found if w.page == page]
    source = document.pages[page - 1].text_source
    return GroundedField(
        raw=field.value,
        evidence=[w.id for w in found],
        page=page,
        box=_union(found),
        grounding="grounded",
        source=source,
        confidence=_confidence(found, source),
    )


def _evidenced_fields(extraction: Extraction) -> Iterator[tuple[str, Evidenced]]:
    for name, value in extraction:
        if isinstance(value, Evidenced):
            yield name, value
    for i, item in enumerate(extraction.line_items):
        for name, value in item:
            yield f"line_items[{i}].{name}", value
    for i, line in enumerate(extraction.tax_lines):
        yield f"tax_lines[{i}].rate", line.rate
        yield f"tax_lines[{i}].amount", line.amount


def ground_extraction(extraction: Extraction, document: ReadDocument) -> dict[str, GroundedField]:
    """Ground every evidenced value. Keys: `vendor_gstin`, `line_items[0].hsn_sac`, ..."""
    by_id = {w.id: w for w in document.words}
    return {
        name: ground_value(field, document, by_id=by_id)
        for name, field in _evidenced_fields(extraction)
    }
