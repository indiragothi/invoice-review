"""The validation step in one pure call: confidence caps, all rules, tidy-up, review status.

`ready` = no blocking error, and every required field is grounded and at or above the
confidence threshold. Anything else is `needs_review`. (`processing`, `failed`, `approved` and
`rejected` belong to the pipeline and the human decision, not to this function.)
"""

from collections.abc import Mapping
from datetime import date
from typing import Literal, cast

from pydantic import BaseModel

from app.clients import Client
from app.config import APP_CONFIG
from app.pipeline.agreement import Agreement
from app.schemas.documents import Invoice, Receipt
from app.schemas.fields import GroundedField
from app.schemas.issues import IssueCode, Severity, ValidationIssue
from app.validation import invoice as invoice_rules
from app.validation import receipt as receipt_rules
from app.validation.agreement import apply_agreement_caps, readings_disagree_issues
from app.validation.confidence import apply_format_caps
from app.validation.duplicates import InvoiceKey, ReceiptKey

ReviewStatus = Literal["ready", "needs_review"]


class ReviewResult(BaseModel):
    status: ReviewStatus
    issues: list[ValidationIssue]
    fields: dict[str, GroundedField]  # with the format caps applied


def required_fields(document: Invoice | Receipt) -> tuple[str, ...]:
    if document.document_type == "invoice":
        return invoice_rules.REQUIRED_FIELDS
    return receipt_rules.REQUIRED_FIELDS


def tidy_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    """Blocking errors first (stable order otherwise), and no low-confidence warning on a field
    that already has an error: the format cap would otherwise report one problem twice."""
    errored = {i.field for i in issues if i.severity == Severity.ERROR and i.field}
    errored |= {i.field for i in issues if i.code == IssueCode.READINGS_DISAGREE and i.field}
    kept = [
        i for i in issues if not (i.code == IssueCode.LOW_CONFIDENCE_FIELD and i.field in errored)
    ]
    return sorted(kept, key=lambda i: i.severity != Severity.ERROR)


def review_status(
    issues: list[ValidationIssue],
    fields: dict[str, GroundedField],
    required: tuple[str, ...],
    threshold: float = APP_CONFIG.confidence_threshold,
) -> ReviewStatus:
    if any(i.severity == Severity.ERROR for i in issues):
        return "needs_review"
    for key in required:
        field = fields.get(key)
        if field is None or field.grounding != "grounded" or field.confidence < threshold:
            return "needs_review"
    return "ready"


def review_document(
    document: Invoice | Receipt,
    fields: dict[str, GroundedField],
    client: Client,
    today: date,
    threshold: float = APP_CONFIG.confidence_threshold,
    existing: Mapping[str, InvoiceKey] | Mapping[str, ReceiptKey] | None = None,
    agreement: Mapping[str, Agreement] | None = None,
) -> ReviewResult:
    """`existing` = duplicate keys of this client's other documents of the same kind.
    `agreement` = per field result of the second reading (None = it did not run)."""
    capped = apply_format_caps(apply_agreement_caps(fields, agreement))
    if isinstance(document, Invoice):
        invoice_keys = cast("Mapping[str, InvoiceKey] | None", existing)
        issues = invoice_rules.validate_invoice(
            document, capped, client, today, threshold, invoice_keys
        )
    else:
        receipt_keys = cast("Mapping[str, ReceiptKey] | None", existing)
        issues = receipt_rules.validate_receipt(document, capped, today, threshold, receipt_keys)
    issues = tidy_issues(issues + readings_disagree_issues(agreement))
    status = review_status(issues, capped, required_fields(document), threshold)
    return ReviewResult(status=status, issues=issues, fields=capped)
