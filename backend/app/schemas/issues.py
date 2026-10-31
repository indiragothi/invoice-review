"""Validation issues. Codes mirror docs/policy-rules.md (snake_case in code)."""

from enum import StrEnum

from pydantic import BaseModel


class Severity(StrEnum):
    ERROR = "error"  # blocking: record cannot be approved while open
    WARNING = "warning"


class IssueCode(StrEnum):
    # Invoice: blocking
    MISSING_VENDOR_NAME = "missing_vendor_name"
    MISSING_INVOICE_NUMBER = "missing_invoice_number"
    MISSING_INVOICE_DATE = "missing_invoice_date"
    INVALID_DATE = "invalid_date"
    AMBIGUOUS_DATE = "ambiguous_date"
    MISSING_TOTAL = "missing_total"
    MISSING_VENDOR_GSTIN = "missing_vendor_gstin"
    INVALID_VENDOR_GSTIN = "invalid_vendor_gstin"
    INVALID_BUYER_GSTIN = "invalid_buyer_gstin"
    BUYER_NOT_CLIENT = "buyer_not_client"
    LINE_ITEMS_SUM_MISMATCH = "line_items_sum_mismatch"
    TOTAL_MISMATCH = "total_mismatch"
    TAX_SPLIT_INCONSISTENT = "tax_split_inconsistent"
    UNGROUNDED_REQUIRED_FIELD = "ungrounded_required_field"
    DUPLICATE_INVOICE = "duplicate_invoice"
    # Invoice: warnings
    MISSING_BUYER_GSTIN = "missing_buyer_gstin"
    MISSING_HSN_SAC = "missing_hsn_sac"
    UNUSUAL_TAX_RATE = "unusual_tax_rate"
    INVOICE_NUMBER_TOO_LONG = "invoice_number_too_long"
    AMOUNT_IN_WORDS_MISMATCH = "amount_in_words_mismatch"
    OLD_INVOICE = "old_invoice"
    REVERSE_CHARGE = "reverse_charge"
    LOW_CONFIDENCE_FIELD = "low_confidence_field"
    READINGS_DISAGREE = "readings_disagree"
    DUPLICATE_FILE = "duplicate_file"
    # Receipt
    MISSING_MERCHANT = "missing_merchant"
    MISSING_RECEIPT_DATE = "missing_receipt_date"
    DUPLICATE_RECEIPT = "duplicate_receipt"
    MISSING_TAX_BREAKUP = "missing_tax_breakup"


class ValidationIssue(BaseModel):
    code: IssueCode
    severity: Severity
    field: str | None = None  # e.g. "vendor_gstin" or "line_items[2].hsn_sac"
    message: str
    suggestion: str | None = None  # e.g. a one-character GSTIN fix; the human accepts it
