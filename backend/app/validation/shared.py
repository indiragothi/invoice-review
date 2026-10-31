"""Checks that invoices and receipts share: dates, GSTINs, grounding and confidence.

Each helper takes the field key (as used by grounding: `"vendor_gstin"`, `"invoice_date"`) so
an issue can point at the exact field on the page.
"""

from datetime import date

from app.config import APP_CONFIG
from app.schemas.documents import NormalisedDate
from app.schemas.fields import GroundedField
from app.schemas.issues import IssueCode, ValidationIssue, make_issue
from app.validation.dates import date_problems
from app.validation.gstin import check_gstin

_GSTIN_PROBLEMS = {
    "length": "is not 15 characters long",
    "format": "does not follow the GSTIN pattern (or its 14th character is not Z)",
    "state": "starts with an unknown state code",
    "pan": "has an invalid PAN part",
    "checksum": "fails the check-character test",
}


def gstin_issue(gstin: str, field: str, invalid_code: IssueCode) -> ValidationIssue | None:
    """An issue if the GSTIN is not valid, with a one-character fix when one exists."""
    result = check_gstin(gstin)
    if result.valid:
        return None
    message = f"GSTIN {gstin} {_GSTIN_PROBLEMS[result.problem or 'format']}."
    suggestion = None
    if result.suggestion:
        suggestion = result.suggestion
        message += f" Did the document print {result.suggestion}?"
    return make_issue(invalid_code, message, field, suggestion)


def date_issues(
    parsed: NormalisedDate, today: date, field: str, missing_code: IssueCode
) -> list[ValidationIssue]:
    messages = {
        "missing": (missing_code, "The date is not printed or was not found."),
        "unreadable": (IssueCode.INVALID_DATE, f"{parsed.raw!r} is not a real date."),
        "future": (IssueCode.INVALID_DATE, f"The date {parsed.value} is in the future."),
        "ambiguous": (
            IssueCode.AMBIGUOUS_DATE,
            f"{parsed.raw!r} could be day-month or month-day; read as {parsed.value}. "
            "Please confirm.",
        ),
        "old": (IssueCode.OLD_INVOICE, f"The date {parsed.value} is more than 12 months old."),
    }
    return [make_issue(*messages[problem], field) for problem in date_problems(parsed, today)]


def ungrounded_issues(
    fields: dict[str, GroundedField], required: tuple[str, ...]
) -> list[ValidationIssue]:
    return [
        make_issue(
            IssueCode.UNGROUNDED_REQUIRED_FIELD,
            f"The value {fields[key].raw!r} was not found in the part of the document the "
            "reader pointed to. Check it against the page.",
            key,
        )
        for key in required
        if key in fields and fields[key].grounding == "ungrounded"
    ]


def low_confidence_issues(
    fields: dict[str, GroundedField],
    required: tuple[str, ...],
    threshold: float = APP_CONFIG.confidence_threshold,
) -> list[ValidationIssue]:
    """Grounded values read with low confidence. Missing / ungrounded ones have their own issue."""
    return [
        make_issue(
            IssueCode.LOW_CONFIDENCE_FIELD,
            f"Read with confidence {fields[key].confidence:.2f} (below {threshold:.2f}). "
            "Please check it.",
            key,
        )
        for key in required
        if key in fields
        and fields[key].grounding == "grounded"
        and fields[key].confidence < threshold
    ]
