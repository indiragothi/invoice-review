from app.schemas.fields import GroundedField
from app.validation.confidence import FORMAT_FAILURE_CAP, apply_format_caps


def field(raw, confidence=1.0, grounding="grounded"):
    return GroundedField(raw=raw, grounding=grounding, confidence=confidence)


def test_a_valid_gstin_keeps_its_confidence():
    capped = apply_format_caps({"vendor_gstin": field("23QSSPM6142B1ZF", 0.9)})
    assert capped["vendor_gstin"].confidence == 0.9


def test_an_invalid_gstin_is_capped_at_0_3():
    capped = apply_format_caps({"vendor_gstin": field("23QMRPW2963E1ZE")})
    assert capped["vendor_gstin"].confidence == FORMAT_FAILURE_CAP == 0.3


def test_a_gstin_with_spaces_and_lower_case_is_judged_after_clean_up():
    capped = apply_format_caps({"buyer_gstin": field("23qssp m6142b1zf")})
    assert capped["buyer_gstin"].confidence == 1.0


def test_an_unreadable_date_is_capped_but_a_real_one_is_not():
    capped = apply_format_caps({"invoice_date": field("31-02-2026"), "other": field("whatever")})
    assert capped["invoice_date"].confidence == 0.3
    assert capped["other"].confidence == 1.0
    ok = apply_format_caps({"invoice_date": field("14-08-2026")})
    assert ok["invoice_date"].confidence == 1.0


def test_an_ambiguous_date_is_still_a_readable_date():
    capped = apply_format_caps({"invoice_date": field("04/05/2026")})
    assert capped["invoice_date"].confidence == 1.0


def test_amounts_that_cannot_be_read_are_capped_including_line_and_tax_cells():
    fields = {
        "total": field("12,3x4.00"),
        "line_items[2].taxable_amount": field("abc"),
        "tax_lines[0].amount": field("9O.00"),
        "round_off": field("-0.34"),
    }
    capped = apply_format_caps(fields)
    assert capped["total"].confidence == 0.3
    assert capped["line_items[2].taxable_amount"].confidence == 0.3
    assert capped["tax_lines[0].amount"].confidence == 0.3
    assert capped["round_off"].confidence == 1.0


def test_the_cap_never_raises_confidence():
    capped = apply_format_caps({"total": field("abc", confidence=0.1)})
    assert capped["total"].confidence == 0.1


def test_missing_values_are_left_alone_and_the_input_is_not_changed():
    original = {"total": field(None, 0.0, "missing"), "invoice_date": field("31-02-2026")}
    capped = apply_format_caps(original)
    assert capped["total"].confidence == 0.0
    assert original["invoice_date"].confidence == 1.0
    assert capped is not original
