"""Printed numbers to Decimal. Never float."""

import re
from decimal import Decimal

_CURRENCY = re.compile(r"(?i)rs\.?|inr|₹")
_PLAIN = re.compile(r"-?\d+(\.\d+)?")
_NUMBER_IN_TEXT = re.compile(r"\d+(?:\.\d+)?")


def parse_amount(text: str | None) -> Decimal | None:
    """`"₹ 1,23,456.00"` -> `Decimal("123456.00")`; `"(0.34)"` and `"-0.34"` are negative.

    Returns None when the text is empty or not a plain number.
    """
    if text is None:
        return None
    cleaned = _CURRENCY.sub("", text)
    cleaned = cleaned.replace(",", "").replace("/-", "")
    cleaned = "".join(cleaned.split())
    cleaned = cleaned.replace("−", "-")  # unicode minus
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    if not _PLAIN.fullmatch(cleaned):
        return None
    return Decimal(cleaned)


def parse_percent(text: str | None) -> Decimal | None:
    """`"9%"`, `"@ 2.5 %"`, `"18"` -> the first number in the text, as a percentage."""
    if text is None:
        return None
    match = _NUMBER_IN_TEXT.search(text.replace(",", ""))
    return Decimal(match.group()) if match else None
