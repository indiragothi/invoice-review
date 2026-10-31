"""Confidence caps that depend on the value itself (docs/policy-rules.md, Confidence).

Base confidence comes from grounding: text layer 1.0, OCR = mean word confidence, ungrounded 0.
Here a value that fails its own format (a GSTIN that is not valid, a date or an amount that
cannot be read) is capped at 0.3. The cap for two readings that disagree (0.5) belongs to the
second reading and arrives with it in M3.

The model's own confidence is never used.
"""

from app.normalisation.amounts import parse_amount
from app.normalisation.dates import parse_date
from app.normalisation.text import normalise_gstin
from app.schemas.fields import GroundedField
from app.validation.gstin import check_gstin

FORMAT_FAILURE_CAP = 0.3

_GSTIN_FIELDS = {"vendor_gstin", "buyer_gstin"}
_DATE_FIELDS = {"invoice_date"}
_AMOUNT_FIELDS = {"taxable_value", "round_off", "total", "taxable_amount", "amount"}


def _fails_its_format(key: str, raw: str) -> bool:
    name = key.rsplit(".", 1)[-1]  # "line_items[2].taxable_amount" -> "taxable_amount"
    if name in _GSTIN_FIELDS:
        gstin = normalise_gstin(raw)
        return gstin is not None and not check_gstin(gstin).valid
    if name in _DATE_FIELDS:
        return parse_date(raw).value is None
    if name in _AMOUNT_FIELDS:
        return parse_amount(raw) is None
    return False


def apply_format_caps(fields: dict[str, GroundedField]) -> dict[str, GroundedField]:
    """A copy of `fields` where values that fail their own format have confidence <= 0.3."""
    capped: dict[str, GroundedField] = {}
    for key, field in fields.items():
        if field.raw and field.raw.strip() and _fails_its_format(key, field.raw):
            field = field.model_copy(
                update={"confidence": min(field.confidence, FORMAT_FAILURE_CAP)}
            )
        capped[key] = field
    return capped
