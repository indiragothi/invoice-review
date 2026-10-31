"""An amount written in words ("Rupees One Lakh Fifteen Thousand Five Hundred Only") to Decimal.

Indian numbering: thousand, lakh (1,00,000), crore (1,00,00,000). Paise may follow either as
"... and Thirty Four Paise Only" or "... and Paise Thirty Four Only". Text that is not a clean
amount in words gives None, so the caller makes no judgement instead of guessing.
"""

import re
from decimal import Decimal

_UNITS = {
    word: number
    for number, word in enumerate(
        (
            "zero one two three four five six seven eight nine ten eleven twelve thirteen "
            "fourteen fifteen sixteen seventeen eighteen nineteen"
        ).split()
    )
}
_TENS = {
    word: number * 10
    for number, word in enumerate(
        "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
    )
    if word != "_"
}
_TENS["fourty"] = 40  # common misspelling
_SCALES = {
    "thousand": 1_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "lacs": 100_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
}
_NOISE = {"rupees", "rupee", "rs", "inr", "only"}
_PAISE = {"paise", "paisa"}


def _number(tokens: list[str]) -> int | None:
    """Words for a whole number, or None if any word is not a number word."""
    if not tokens:
        return None
    total = current = 0
    for token in tokens:
        if token in _UNITS:
            current += _UNITS[token]
        elif token in _TENS:
            current += _TENS[token]
        elif token == "hundred":
            current = (current or 1) * 100
        elif token in _SCALES:
            total += (current or 1) * _SCALES[token]
            current = 0
        else:
            return None
    return total + current


def parse_amount_in_words(text: str | None) -> Decimal | None:
    if not text:
        return None
    tokens = [t for t in re.split(r"[\s\-,.]+", text.casefold()) if t and t not in _NOISE]

    paise = 0
    if any(t in _PAISE for t in tokens):
        at = next(i for i, t in enumerate(tokens) if t in _PAISE)
        after = tokens[at + 1 :]
        if after:  # "... and Paise Thirty Four"
            paise_words, tokens = after, tokens[:at]
        else:  # "... and Thirty Four Paise"
            before = tokens[:at]
            if "and" not in before:
                return None
            cut = len(before) - 1 - before[::-1].index("and")
            paise_words, tokens = before[cut + 1 :], before[:cut]
        paise_value = _number(paise_words)
        if paise_value is None or paise_value > 99:
            return None
        paise = paise_value

    rupees = _number([t for t in tokens if t != "and"])
    if rupees is None:
        return None
    return Decimal(rupees) + Decimal(paise) / 100
