"""What the second reading changes in the validation (docs/policy-rules.md, Confidence).

- Readings that differ: confidence at most 0.5 and a `READINGS_DISAGREE` warning for the field.
- A value that only the second reading supplied (`filled`): confidence at most 0.5 as well, since
  just one reading saw it. The reviewer confirms it.
- `agree` and `missing` change nothing. An edited field is the human's and is no longer compared.

Pure: no I/O, no model calls.
"""

from collections.abc import Mapping

from app.pipeline.agreement import Agreement
from app.schemas.fields import GroundedField
from app.schemas.issues import IssueCode, ValidationIssue, make_issue

DISAGREEMENT_CAP = 0.5
_CAPPED = {"differ", "filled"}


def apply_agreement_caps(
    fields: Mapping[str, GroundedField], agreement: Mapping[str, Agreement] | None
) -> dict[str, GroundedField]:
    """A copy of `fields` where disputed or single-sourced values have confidence <= 0.5."""
    capped: dict[str, GroundedField] = {}
    for path, field in fields.items():
        if agreement and agreement.get(path) in _CAPPED:
            field = field.model_copy(update={"confidence": min(field.confidence, DISAGREEMENT_CAP)})
        capped[path] = field
    return capped


def readings_disagree_issues(agreement: Mapping[str, Agreement] | None) -> list[ValidationIssue]:
    """One warning per field (or table) on which the two readings differ."""
    if not agreement:
        return []
    return [
        make_issue(
            IssueCode.READINGS_DISAGREE,
            f"The two readings of {path} differ; check the value against the page.",
            path,
        )
        for path, status in agreement.items()
        if status == "differ"
    ]
