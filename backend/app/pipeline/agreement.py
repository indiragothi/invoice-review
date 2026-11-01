"""Compare the two readings and fill gaps (docs/architecture.md, step 4 "document review").

Reading A is the numbered-words extraction; reading B is an independent look at the page images.
Per field the result is one of:

- `agree`   both readings have the same value (compared after normalisation);
- `differ`  both have a value and they are not the same;
- `missing` one reading has no value (A has one that B did not see, or B has one that cannot be
            found in the page words);
- `filled`  A had no value, B has one, and code found it in the page words (so it has a box).

A value from B is never trusted on its own word: `fill_gaps` only uses it when the text really
appears in the words of the page. Pure code: no I/O, no model calls.
"""

import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Literal

from app.normalisation.amounts import parse_amount, parse_percent
from app.normalisation.dates import parse_date
from app.normalisation.states import state_code_from_text
from app.normalisation.text import normalise_gstin
from app.pipeline.grounding import _evidenced_fields, _squash, _windows
from app.reader.schemas import ReadDocument
from app.schemas.extraction import Evidenced, Extraction
from app.schemas.fields import GroundedField
from app.schemas.second_reading import SecondReading

Agreement = Literal["agree", "differ", "missing", "filled"]
_Raw = Literal["agree", "differ", "missing", "b_only"]  # before the gap search

_PERCENT = {"gst_rate"}
_AMOUNT = {"taxable_value", "round_off", "total", "taxable_amount"}
_FUZZY_TEXT = {"vendor_name", "buyer_name", "description"}
_MIN_CONTAINED = 5  # "Sai Stationery" inside "Sai Stationery Mart": only for longer names


def _leaf(path: str) -> str:
    return path.rsplit(".", 1)[-1]


def _leading_number(text: str):
    """The number at the start of a quantity: '20 ream' and '20' are the same 20."""
    match = re.match(r"\s*(\d[\d,]*(?:\.\d+)?|\.\d+)", text)
    return parse_amount(match.group(1)) if match else None


def _tidy(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", text.casefold())


def _same(path: str, a: str, b: str) -> bool:
    """Are two printed values the same thing? Compared after normalisation."""
    leaf = _leaf(path)
    if leaf in {"vendor_gstin", "buyer_gstin"}:
        return normalise_gstin(a) == normalise_gstin(b)
    if leaf == "invoice_date":
        da, db = parse_date(a), parse_date(b)
        return da.value is not None and da.value == db.value
    if leaf == "place_of_supply":
        return state_code_from_text(a) is not None and state_code_from_text(a) == (
            state_code_from_text(b)
        )
    if leaf == "rate" and path.startswith("tax_lines") or leaf in _PERCENT:
        return parse_percent(a) is not None and parse_percent(a) == parse_percent(b)
    if leaf == "quantity":
        qa, qb = _leading_number(a), _leading_number(b)
        return qa == qb if qa is not None and qb is not None else _tidy(a) == _tidy(b)
    if leaf in _AMOUNT or leaf in {"amount", "rate"}:
        return parse_amount(a) is not None and parse_amount(a) == parse_amount(b)
    if leaf == "hsn_sac":
        return _tidy(a) == _tidy(b)
    x, y = _tidy(a), _tidy(b)
    if leaf in _FUZZY_TEXT and min(len(x), len(y)) >= _MIN_CONTAINED:
        return x in y or y in x
    return x == y


def _b_values(b: SecondReading) -> dict[str, str | None]:
    """Reading B under the same paths as reading A."""
    values: dict[str, str | None] = {}
    for name, value in b:
        if isinstance(value, str) or value is None:
            values[name] = value
    for i, item in enumerate(b.line_items):
        for name, value in item:
            values[f"line_items[{i}].{name}"] = value
    for i, line in enumerate(b.tax_lines):
        values[f"tax_lines[{i}].rate"] = line.rate
        values[f"tax_lines[{i}].amount"] = line.amount
    return values


def _a_values(a: Extraction) -> dict[str, Evidenced]:
    return dict(_evidenced_fields(a))


def _clean(value: str | None) -> str | None:
    return value.strip() or None if value else None


def _compare(a: Extraction, b: SecondReading) -> dict[str, _Raw]:
    a_fields, b_values = _a_values(a), _b_values(b)
    result: dict[str, _Raw] = {}
    for path, field in a_fields.items():
        a_val = _clean(field.value)
        # Rows that exist in only one reading are reported once, below, as `line_items`.
        if path not in b_values and path.startswith(("line_items[", "tax_lines[")):
            continue
        b_val = _clean(b_values.get(path))
        if a_val is None and b_val is None:
            continue
        if path == "round_off":  # "no round off" and "0.00" are the same thing
            a_val, b_val = a_val or "0", b_val or "0"
        if a_val is None:
            result[path] = "b_only"
        elif b_val is None:
            result[path] = "missing"
        else:
            result[path] = "agree" if _same(path, a_val, b_val) else "differ"
    if len(a.line_items) != len(b.line_items):
        result["line_items"] = "differ"
    if len(a.tax_lines) != len(b.tax_lines):
        result["tax_lines"] = "differ"
    return result


def locate_value(document: ReadDocument, value: str) -> list[str] | None:
    """IDs of the words that make up `value` on one line of the page, or None if it is not there.

    Compared like grounding does (ignoring spaces and case), with the whole value as the target,
    so a number is never found inside a longer one. The first match in reading order wins."""
    target = _squash(value)
    if not target:
        return None
    lines: dict[tuple[int, int], list] = {}
    for word in document.words:
        lines.setdefault((word.page, word.line), []).append(word)
    for key in sorted(lines):
        for window in _windows(lines[key], target, exact=True):
            return [w.id for w in window]
    return None


def compare_and_fill(
    a: Extraction, b: SecondReading, document: ReadDocument
) -> tuple[Extraction, dict[str, Agreement]]:
    """The merged extraction (gaps filled from B where B's value is in the page words) and the
    agreement per field. Reading A's own values are never replaced."""
    raw = _compare(a, b)
    b_values = _b_values(b)
    merged = a.model_dump()
    agreement: dict[str, Agreement] = {}
    for path, status in raw.items():
        if status != "b_only":
            agreement[path] = status
            continue
        text = _clean(b_values[path])
        words = locate_value(document, text) if text else None
        if text is None or words is None:
            agreement[path] = "missing"
            continue
        _set(merged, path, text, words)
        agreement[path] = "filled"
    return Extraction.model_validate(merged), agreement


_LINE = re.compile(r"^line_items\[(\d+)\]\.(\w+)$")
_TAX = re.compile(r"^tax_lines\[(\d+)\]\.(\w+)$")


def _set(data: dict, path: str, value: str, words: list[str]) -> None:
    if m := _LINE.match(path):
        target = data["line_items"][int(m[1])][m[2]]
    elif m := _TAX.match(path):
        target = data["tax_lines"][int(m[1])][m[2]]
    else:
        target = data[path]
    target["value"], target["evidence"] = value, words


def disagreeing_paths(agreement: Mapping[str, Agreement]) -> Iterator[str]:
    return (path for path, status in agreement.items() if status == "differ")


def in_doubt(
    fields: Mapping[str, GroundedField], required: Sequence[str], threshold: float
) -> bool:
    """Is a required field missing, not found in the words, or below the confidence threshold?
    That is when `SECOND_READING=on_doubt` spends the extra call."""
    for key in required:
        field = fields.get(key)
        if field is None or field.grounding != "grounded" or field.confidence < threshold:
            return True
    return False
