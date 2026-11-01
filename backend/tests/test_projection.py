import pytest

from app.documents.projection import (
    InvalidValueError,
    UnknownFieldError,
    apply_edits,
    build_review_data,
    extraction_with_values,
    grounded_fields,
    refresh_review_data,
)
from app.schemas.extraction import Evidenced, ExtractedLineItem, ExtractedTaxLine, Extraction
from app.schemas.fields import GroundedField


def ev(value: str | None) -> Evidenced:
    return Evidenced(value=value, evidence=["w1"] if value else [])


def extraction() -> Extraction:
    line = ExtractedLineItem(
        description=ev("Paper"),
        hsn_sac=ev("4802"),
        quantity=ev("2"),
        rate=ev("50"),
        gst_rate=ev("12"),
        taxable_amount=ev("100"),
    )
    return Extraction(
        document_type="invoice",
        classification_reason="x",
        vendor_name=ev("Sai Stationery"),
        vendor_gstin=ev("23QSSPM6142B1ZF"),
        buyer_name=ev(None),
        buyer_gstin=ev(None),
        invoice_number=ev("INV-1"),
        invoice_date=ev("14-08-2026"),
        place_of_supply=ev(None),
        line_items=[line],
        taxable_value=ev("100"),
        tax_lines=[ExtractedTaxLine(head="CGST", rate=ev("6"), amount=ev("6"))],
        round_off=ev(None),
        total=ev("112"),
        amount_in_words=ev(None),
    )


def grounded() -> dict[str, GroundedField]:
    return {
        "vendor_gstin": GroundedField(
            raw="23QSSPM6142B1ZF",
            evidence=["w5"],
            page=1,
            box=(1, 2, 3, 4),
            grounding="grounded",
            source="ocr",
            confidence=0.7,
        ),
        "buyer_gstin": GroundedField(raw=None, grounding="missing", confidence=0.0),
        "line_items[0].taxable_amount": GroundedField(
            raw="100",
            evidence=["w9"],
            page=1,
            box=(5, 6, 7, 8),
            grounding="grounded",
            source="pdf_text",
            confidence=1.0,
        ),
        "tax_lines[0].amount": GroundedField(
            raw="6",
            evidence=["w11"],
            page=1,
            box=(9, 9, 9, 9),
            grounding="grounded",
            source="pdf_text",
            confidence=1.0,
        ),
    }


def test_review_data_round_trips_to_the_same_grounded_fields():
    data = build_review_data(grounded())
    assert data["fields"]["vendor_gstin"]["evidence"] == {
        "page": 1,
        "word_ids": ["w5"],
        "box": (1, 2, 3, 4),
    }
    assert grounded_fields(data) == grounded()


def test_an_edit_makes_the_field_human_with_full_confidence_and_keeps_the_original():
    data = build_review_data(grounded())
    edited, changes = apply_edits(data, {"vendor_gstin": " 23QXGPS4821K1ZU "})
    entry = edited["fields"]["vendor_gstin"]
    assert entry["value"] == "23QXGPS4821K1ZU" and entry["original"] == "23QSSPM6142B1ZF"
    assert (entry["source"], entry["confidence"], entry["grounding"]) == ("human", 1.0, "grounded")
    assert changes == {"vendor_gstin": {"from": "23QSSPM6142B1ZF", "to": "23QXGPS4821K1ZU"}}
    assert data["fields"]["vendor_gstin"]["source"] == "ocr"  # the input is not changed


def test_clearing_a_field_makes_it_missing_and_filling_a_missing_one_makes_it_grounded():
    data = build_review_data(grounded())
    edited, _ = apply_edits(data, {"vendor_gstin": "  ", "buyer_gstin": "27QWRCA7310M1ZK"})
    assert edited["fields"]["vendor_gstin"]["value"] is None
    assert edited["fields"]["vendor_gstin"]["grounding"] == "missing"
    assert edited["fields"]["buyer_gstin"]["grounding"] == "grounded"
    assert edited["fields"]["buyer_gstin"]["source"] == "human"


def test_an_unchanged_value_is_not_an_edit():
    data = build_review_data(grounded())
    edited, changes = apply_edits(data, {"vendor_gstin": "23QSSPM6142B1ZF"})
    assert changes == {} and edited["fields"]["vendor_gstin"]["source"] == "ocr"


def test_unknown_paths_and_bad_values_are_rejected_without_a_partial_edit():
    data = build_review_data(grounded())
    with pytest.raises(UnknownFieldError):
        apply_edits(data, {"vendor_gstin": "x", "line_items[7].hsn_sac": "1"})
    with pytest.raises(InvalidValueError):
        apply_edits(data, {"vendor_gstin": "x" * 501})
    with pytest.raises(InvalidValueError):
        apply_edits(data, {"vendor_gstin": 12})  # type: ignore[dict-item]


def test_extraction_takes_the_review_values_by_path():
    data = build_review_data(grounded())
    edited, _ = apply_edits(
        data, {"vendor_gstin": "27QWRCA7310M1ZK", "line_items[0].taxable_amount": "250"}
    )
    result = extraction_with_values(extraction(), edited)
    assert result.vendor_gstin.value == "27QWRCA7310M1ZK"
    assert result.line_items[0].taxable_amount.value == "250"
    assert result.tax_lines[0].amount.value == "6"
    assert result.vendor_name.value == "Sai Stationery"  # not in review_data: untouched


def test_extraction_with_an_unknown_path_fails_instead_of_ignoring_it():
    data = {"fields": {"line_items[3].hsn_sac": {"value": "1"}}}
    with pytest.raises(UnknownFieldError):
        extraction_with_values(extraction(), data)


def test_refresh_keeps_the_original_reading_after_an_edit_and_a_cap():
    data = build_review_data(grounded())
    edited, _ = apply_edits(data, {"vendor_gstin": "23QXGPS4821K1ZU"})
    capped = grounded_fields(edited)
    capped["vendor_gstin"] = capped["vendor_gstin"].model_copy(update={"confidence": 0.3})
    refreshed = refresh_review_data(edited, capped)
    entry = refreshed["fields"]["vendor_gstin"]
    assert entry["original"] == "23QSSPM6142B1ZF"  # the model's reading, not the edit
    assert entry["value"] == "23QXGPS4821K1ZU" and entry["confidence"] == 0.3
    assert entry["source"] == "human"
