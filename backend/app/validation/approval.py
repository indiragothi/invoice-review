"""The approval invariant as a pure function (docs/policy-rules.md, Invariants).

A record can become `approved` only if it is `ready`, has no open blocking error, and has a valid
selected ledger. The service calls this before every approval, single or bulk, so the rule does
not depend on the UI or on which route was used. A decided record is locked.
"""

from collections.abc import Sequence

from app.accounting.catalog import checked_ledger_code
from app.schemas.issues import Severity, ValidationIssue

DECIDED = ("approved", "rejected")
CAN_BE_REJECTED = ("ready", "needs_review")


def approval_blockers(
    status: str, issues: Sequence[ValidationIssue], selected_ledger_code: str | None
) -> list[str]:
    """Why this record cannot be approved. An empty list means it can."""
    if status in DECIDED:
        return [f"The record is already {status} and locked."]
    blockers: list[str] = []
    if status != "ready":
        blockers.append(f"Status is {status}; only a ready document can be approved.")
    errors = sorted({i.code.value for i in issues if i.severity == Severity.ERROR})
    if errors:
        blockers.append(f"Open blocking errors: {', '.join(errors)}.")
    if checked_ledger_code(selected_ledger_code) is None:
        blockers.append("Select a ledger before approving.")
    return blockers


def rejection_blockers(status: str) -> list[str]:
    if status in DECIDED:
        return [f"The record is already {status} and locked."]
    if status not in CAN_BE_REJECTED:
        return [f"Status is {status}; only a ready or needs_review document can be rejected."]
    return []
