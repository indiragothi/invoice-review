"""`review_data`: the flat, editable view of a document (docs/architecture.md section 7).

One entry per extracted value, addressed by path: `vendor_gstin`, `line_items[2].taxable_amount`,
`tax_lines[0].amount`. Pure functions, no policy: they only move values between the grounded
fields, the stored JSON and the extraction that the rules read.

Entry shape:

    {"value": "27ABC...", "original": "27ABC...", "source": "pdf_text" | "ocr" | "human",
     "confidence": 0.93, "grounding": "grounded", "agreement": null,
     "evidence": {"page": 1, "word_ids": ["w41"], "box": [412, 88, 590, 104]}}

`value` is what the rules see; `original` is the model's reading, kept for the audit trail.
"""

import re
from collections.abc import Mapping
from typing import Any

from app.schemas.extraction import Extraction
from app.schemas.fields import GroundedField

MAX_VALUE_LENGTH = 500

_TOP = re.compile(r"^(?P<name>[a-z_]+)$")
_LINE = re.compile(r"^line_items\[(?P<i>\d+)\]\.(?P<name>[a-z_]+)$")
_TAX = re.compile(r"^tax_lines\[(?P<i>\d+)\]\.(?P<name>rate|amount)$")


class UnknownFieldError(ValueError):
    """The path is not a field of this document."""


class InvalidValueError(ValueError):
    pass


def build_review_data(
    fields: Mapping[str, GroundedField], agreement: Mapping[str, str] | None = None
) -> dict[str, Any]:
    agreement = agreement or {}
    return {
        "fields": {
            path: {
                "value": field.raw,
                "original": field.raw,
                "source": field.source,
                "confidence": field.confidence,
                "grounding": field.grounding,
                "agreement": agreement.get(path),
                "evidence": {"page": field.page, "word_ids": field.evidence, "box": field.box},
            }
            for path, field in fields.items()
        }
    }


def refresh_review_data(
    previous: Mapping[str, Any], fields: Mapping[str, GroundedField]
) -> dict[str, Any]:
    """After re-validation (format caps applied): the new field states, with the model's
    original reading and the agreement carried over from `previous`."""
    refreshed = build_review_data(fields)
    for path, entry in refreshed["fields"].items():
        old = previous["fields"].get(path)
        if old is not None:
            entry["original"] = old["original"]
            entry["agreement"] = old["agreement"]
    return refreshed


def agreement_of(review_data: Mapping[str, Any]) -> dict[str, str]:
    """The second-reading result per field, from `review_data`. A field the reviewer edited has
    none: it is the human's value and is no longer compared."""
    return {
        path: entry["agreement"]
        for path, entry in review_data["fields"].items()
        if entry.get("agreement") and entry["source"] != "human"
    }


def grounded_fields(review_data: Mapping[str, Any]) -> dict[str, GroundedField]:
    """Back to the models the rules read. `value` becomes `raw` (the text the rules check)."""
    result: dict[str, GroundedField] = {}
    for path, entry in review_data["fields"].items():
        evidence = entry["evidence"]
        result[path] = GroundedField(
            raw=entry["value"],
            evidence=evidence["word_ids"],
            page=evidence["page"],
            box=tuple(evidence["box"]) if evidence["box"] else None,
            grounding=entry["grounding"],
            source=entry["source"],
            confidence=entry["confidence"],
        )
    return result


def apply_edits(
    review_data: Mapping[str, Any], edits: Mapping[str, str | None]
) -> tuple[dict[str, Any], dict[str, dict[str, str | None]]]:
    """Return a new review_data with the edits applied, and `{path: {"from", "to"}}` for the
    values that really changed. An edited field is the human's: source `human`, confidence 1.0,
    grounded (or missing when the reviewer cleared it). Nothing is changed on any error."""
    fields = {path: dict(entry) for path, entry in review_data["fields"].items()}
    changes: dict[str, dict[str, str | None]] = {}
    for path, raw_value in edits.items():
        if path not in fields:
            raise UnknownFieldError(path)
        value = _clean(path, raw_value)
        entry = fields[path]
        if value == entry["value"] and entry["source"] == "human":
            continue  # already the reviewer's value: nothing to record
        # The same value sent for a field the reviewer has not yet touched is a confirmation:
        # they looked at the page and agree. It becomes theirs, and its warnings go.
        changes[path] = {"from": entry["value"], "to": value}
        entry.update(
            value=value,
            source="human",
            confidence=1.0,
            grounding="grounded" if value else "missing",
            agreement=None,
        )
    return {"fields": fields}, changes


def _clean(path: str, value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidValueError(f"{path}: the value must be text.")
    if len(value) > MAX_VALUE_LENGTH:
        raise InvalidValueError(f"{path}: longer than {MAX_VALUE_LENGTH} characters.")
    cleaned = value.strip()
    return cleaned or None


def extraction_with_values(extraction: Extraction, review_data: Mapping[str, Any]) -> Extraction:
    """The extraction with every value replaced by the (possibly edited) review value."""
    data = extraction.model_dump()
    for path, entry in review_data["fields"].items():
        _target(data, path)["value"] = entry["value"]
    return Extraction.model_validate(data)


def _target(data: dict[str, Any], path: str) -> dict[str, Any]:
    try:
        if match := _LINE.match(path):
            return data["line_items"][int(match["i"])][match["name"]]
        if match := _TAX.match(path):
            return data["tax_lines"][int(match["i"])][match["name"]]
        if _TOP.match(path):
            target = data[path]
            if isinstance(target, dict) and "value" in target:
                return target
    except (KeyError, IndexError):
        pass
    raise UnknownFieldError(path)
