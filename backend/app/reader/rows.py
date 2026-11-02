"""Reading rows on a tilted scan. Pure functions: no OCR, no images.

OCR returns each table cell as its own text line, ordered by height. On a page tilted by a few
degrees the right end of a table row sits higher than its left end, so the amount of a row comes
before its rate and a model pairs the numbers wrongly (sample 20). The fix is to measure the tilt
from the OCR text boxes and to group words into rows after undoing it. Only the line numbering
changes: word IDs and boxes stay as they are.
"""

import math
from collections.abc import Sequence
from statistics import median

Point = Sequence[float]
MAX_TILT_DEGREES = 10.0  # beyond this the page is treated as untilted (a wrong estimate is worse)
LONG_LINE_RATIO = 4.0  # only lines this much longer than high say anything about the tilt
ROW_TOLERANCE = 0.5  # words whose corrected centres are within this share of a line's height


def estimate_tilt(quads: Sequence[Sequence[Point]]) -> tuple[float, float]:
    """(tilt in radians, typical line height) from the text boxes OCR found.

    Each quad is four corners: top-left, top-right, bottom-right, bottom-left. The tilt is the
    median slope of the top edge of the long lines; positive means the text slopes down to the
    right. Without long lines, or with an implausible angle, the tilt is 0."""
    angles: list[float] = []
    heights: list[float] = []
    for quad in quads:
        if len(quad) != 4:
            continue
        tl, tr, _, bl = quad
        width = math.hypot(tr[0] - tl[0], tr[1] - tl[1])
        height = math.hypot(bl[0] - tl[0], bl[1] - tl[1])
        if height <= 0:
            continue
        heights.append(height)
        if width >= LONG_LINE_RATIO * height:
            angles.append(math.atan2(tr[1] - tl[1], tr[0] - tl[0]))
    line_height = median(heights) if heights else 1.0
    if not angles:
        return 0.0, line_height
    tilt = median(angles)
    if abs(math.degrees(tilt)) > MAX_TILT_DEGREES:
        return 0.0, line_height
    return tilt, line_height


def assign_rows(
    centres: Sequence[tuple[float, float]], tilt: float, line_height: float
) -> list[int]:
    """A row number per centre (0 = top row), after undoing the tilt.

    Walks the centres from the top and starts a new row when a centre is further than half a
    line height from the mean of the current row."""
    if not centres:
        return []
    cos, sin = math.cos(tilt), math.sin(tilt)
    corrected = [y * cos - x * sin for x, y in centres]
    limit = ROW_TOLERANCE * max(line_height, 1.0)
    rows = [0] * len(centres)
    row = 0
    members: list[float] = []
    for index in sorted(range(len(centres)), key=corrected.__getitem__):
        value = corrected[index]
        if members and abs(value - sum(members) / len(members)) > limit:
            row += 1
            members = []
        members.append(value)
        rows[index] = row
    return rows
