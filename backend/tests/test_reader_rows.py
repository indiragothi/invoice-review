import math

from app.reader.rows import assign_rows, estimate_tilt


def quad(x, y, width, height, angle=0.0):
    """Corners of a text box whose top edge starts at (x, y) and slopes by `angle` radians."""
    dx, dy = math.cos(angle), math.sin(angle)
    top_right = (x + width * dx, y + width * dy)
    return [(x, y), top_right, (top_right[0] - height * dy, top_right[1] + height * dx),
            (x - height * dy, y + height * dx)]


def test_no_text_boxes_means_no_tilt():
    assert estimate_tilt([]) == (0.0, 1.0)


def test_the_tilt_is_the_median_slope_of_the_long_lines():
    angle = math.radians(-4.5)
    quads = [quad(100, 300 + 40 * i, 400, 20, angle) for i in range(5)]
    quads.append(quad(50, 50, 30, 20))  # a short word says nothing about the tilt
    tilt, height = estimate_tilt(quads)
    assert math.isclose(tilt, angle, abs_tol=1e-6)
    assert math.isclose(height, 20, abs_tol=1e-6)


def test_an_implausible_tilt_is_ignored():
    assert estimate_tilt([quad(0, 0, 400, 20, math.radians(30))])[0] == 0.0


def test_a_row_of_a_tilted_table_is_one_row():
    # Sample 20: the amount (right) is 15 px higher than the rate (middle) in the same row.
    tilt = math.radians(-4.5)
    rate, amount = (780, 399), (990, 384)
    next_rate, next_amount = (780, 431), (990, 416)
    rows = assign_rows([amount, rate, next_amount, next_rate], tilt, 24)
    assert rows[0] == rows[1]
    assert rows[2] == rows[3]
    assert rows[0] != rows[2]


def test_without_the_correction_the_same_words_would_be_split():
    rate, amount = (780, 399), (990, 384)
    assert assign_rows([amount, rate], 0.0, 24)[0] != assign_rows([amount, rate], 0.0, 24)[1]


def test_rows_are_numbered_from_the_top():
    assert assign_rows([(10, 300), (10, 100), (10, 200)], 0.0, 20) == [2, 0, 1]


def test_nothing_in_nothing_out():
    assert assign_rows([], 0.0, 20) == []
