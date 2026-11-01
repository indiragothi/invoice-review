"""Which issues the supplier can fix (docs/policy-rules.md, Correction requests).

A fixed set of codes, not a model decision. Not eligible (our problem, not the supplier's):
`UNGROUNDED_REQUIRED_FIELD`, `AMBIGUOUS_DATE`, `LOW_CONFIDENCE_FIELD`, `READINGS_DISAGREE`, the
duplicates, and everything else not listed here.
"""

from collections.abc import Sequence

from app.schemas.issues import IssueCode, ValidationIssue

SUPPLIER_FIXABLE: frozenset[IssueCode] = frozenset(
    {
        IssueCode.MISSING_VENDOR_GSTIN,
        IssueCode.INVALID_VENDOR_GSTIN,
        IssueCode.INVALID_BUYER_GSTIN,
        IssueCode.BUYER_NOT_CLIENT,
        IssueCode.MISSING_BUYER_GSTIN,
        IssueCode.MISSING_INVOICE_NUMBER,
        IssueCode.INVOICE_NUMBER_TOO_LONG,
        IssueCode.MISSING_INVOICE_DATE,
        IssueCode.MISSING_TOTAL,
        IssueCode.LINE_ITEMS_SUM_MISMATCH,
        IssueCode.TOTAL_MISMATCH,
        IssueCode.TAX_SPLIT_INCONSISTENT,
        IssueCode.MISSING_HSN_SAC,
        IssueCode.AMOUNT_IN_WORDS_MISMATCH,
    }
)


def is_supplier_fixable(code: IssueCode) -> bool:
    return code in SUPPLIER_FIXABLE


def eligible_issues(issues: Sequence[ValidationIssue]) -> list[ValidationIssue]:
    return [issue for issue in issues if issue.code in SUPPLIER_FIXABLE]
