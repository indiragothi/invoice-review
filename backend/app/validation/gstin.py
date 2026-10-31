"""GSTIN validation: format, state code, PAN part and checksum. Offline, pure code.

We do not claim the GSTIN is active: that needs the GST portal (out of scope).

The checks follow `python-stdnum` (`in_.gstin`) but use our own state table, because stdnum's
list lacks 38 (Ladakh), 97 and 99. Codes 25 and 28 (old Daman and Diu, old Andhra Pradesh)
are still accepted as legacy so an old registration is not rejected.
"""

import re
from dataclasses import dataclass
from typing import Literal

from stdnum import luhn
from stdnum.exceptions import ValidationError
from stdnum.in_ import pan

from app.normalisation.states import STATE_CODES

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
ACCEPTED_STATE_CODES = frozenset(STATE_CODES) | {"25", "28"}
_FORMAT = re.compile(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]{3}")

# Characters OCR often mixes up (docs/policy-rules.md). Each maps to its look-alikes.
CONFUSABLE: dict[str, str] = {
    "0": "O",
    "O": "0",
    "1": "I",
    "I": "1",
    "5": "S",
    "S": "5",
    "8": "B",
    "B": "8",
}

Problem = Literal["length", "format", "state", "pan", "checksum"]


@dataclass(frozen=True)
class GstinCheck:
    valid: bool
    problem: Problem | None = None
    suggestion: str | None = None  # a full GSTIN that passes; the human accepts it, never code


def _problem(gstin: str) -> Problem | None:
    if len(gstin) != 15:
        return "length"
    if not _FORMAT.fullmatch(gstin) or gstin[12] == "0" or gstin[13] != "Z":
        return "format"
    if gstin[:2] not in ACCEPTED_STATE_CODES:
        return "state"
    try:
        pan.validate(gstin[2:12])
    except ValidationError:
        return "pan"
    try:
        luhn.validate(gstin, ALPHABET)
    except ValidationError:
        return "checksum"
    return None


def suggest_fix(gstin: str) -> str | None:
    """A one-character fix that makes the GSTIN fully valid, or None. Never applied by code.

    1. An OCR look-alike swap (0/O, 1/I, 5/S, 8/B), only when exactly one swap works: with two
       or more we would be guessing.
    2. Otherwise, if everything but the checksum is fine, the check character that the first
       14 characters call for (the typical typo is in the last character). Many other single
       characters could be the wrong one, so the reviewer must compare with the document.

    A GSTIN of the wrong length is not touched (a dropped or extra character is not a swap).
    """
    if len(gstin) != 15:
        return None
    candidates = {
        gstin[:i] + alternative + gstin[i + 1 :]
        for i, char in enumerate(gstin)
        if (alternative := CONFUSABLE.get(char))
    }
    working = [c for c in candidates if _problem(c) is None]
    if len(working) == 1:
        return working[0]
    if _problem(gstin) == "checksum":
        return gstin[:14] + luhn.calc_check_digit(gstin[:14], ALPHABET)
    return None


def check_gstin(gstin: str) -> GstinCheck:
    """Expects a normalised GSTIN (upper-case, no spaces): see `normalise_gstin`."""
    problem = _problem(gstin)
    if problem is None:
        return GstinCheck(valid=True)
    return GstinCheck(valid=False, problem=problem, suggestion=suggest_fix(gstin))
