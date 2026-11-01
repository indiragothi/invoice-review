from app.pipeline.agreement import compare_and_fill, locate_value
from app.reader.schemas import Page, ReadDocument, Word
from app.schemas.extraction import Evidenced, ExtractedLineItem, ExtractedTaxLine, Extraction
from app.schemas.fields import GroundedField
from app.schemas.issues import IssueCode, Severity
from app.schemas.second_reading import SecondLineItem, SecondReading, SecondTaxLine
from app.validation.agreement import apply_agreement_caps, readings_disagree_issues


def ev(value: str | None, *ids: str) -> Evidenced:
    return Evidenced(value=value, evidence=list(ids) if value else [])


def extraction(**changes) -> Extraction:
    line = ExtractedLineItem(
        description=ev("Copier paper A4", "w20"),
        hsn_sac=ev("4802", "w21"),
        quantity=ev("2", "w22"),
        rate=ev("500.00", "w23"),
        gst_rate=ev("12%", "w24"),
        taxable_amount=ev("1,000.00", "w25"),
    )
    base = dict(
        document_type="invoice",
        classification_reason="x",
        vendor_name=ev("Sai Stationery Mart", "w1", "w2", "w3"),
        vendor_gstin=ev("23QSSPM6142B1ZF", "w5"),
        buyer_name=ev(None),
        buyer_gstin=ev(None),
        invoice_number=ev("INV/26-27/001", "w8"),
        invoice_date=ev("14-08-2026", "w10"),
        place_of_supply=ev("Madhya Pradesh (23)", "w12"),
        line_items=[line],
        taxable_value=ev("1,000.00", "w30"),
        tax_lines=[ExtractedTaxLine(head="CGST", rate=ev("6", "w31"), amount=ev("60.00", "w32"))],
        round_off=ev(None),
        total=ev("1,120.00", "w40"),
        amount_in_words=ev(None),
    )
    return Extraction(**{**base, **changes})


def reading_b(**changes) -> SecondReading:
    base = dict(
        vendor_name="SAI STATIONERY MART",
        vendor_gstin="23 QSSPM6142B1ZF",
        buyer_name=None,
        buyer_gstin=None,
        invoice_number="inv/26-27/001",
        invoice_date="14/08/2026",
        place_of_supply="Madhya Pradesh",
        line_items=[
            SecondLineItem(
                description="Copier paper A4",
                hsn_sac="4802",
                quantity="2",
                rate="500",
                gst_rate="12",
                taxable_amount="1000",
            )
        ],
        taxable_value="1000.00",
        tax_lines=[SecondTaxLine(head="CGST", rate="6.0", amount="60")],
        round_off="0.00",
        total="1,120",
        amount_in_words=None,
    )
    return SecondReading(**{**base, **changes})


def document(*lines: str) -> ReadDocument:
    """Each argument is one printed line; its words are numbered w1, w2, ... across the page."""
    words: list[Word] = []
    for line_number, line in enumerate(lines, start=1):
        for text in line.split():
            words.append(
                Word(
                    id=f"w{len(words) + 1}",
                    page=1,
                    line=line_number,
                    text=text,
                    box=(0, 0, 1, 1),
                    confidence=1.0,
                )
            )
    return ReadDocument(
        content_type="application/pdf",
        pages=[Page(number=1, width=100, height=100, text_source="pdf_text")],
        words=words,
    )


DOC = document("Rajwada Properties")


def test_the_same_values_in_other_notation_agree():
    _, agreement = compare_and_fill(extraction(), reading_b(), DOC)
    assert agreement["vendor_name"] == "agree"  # case
    assert agreement["vendor_gstin"] == "agree"  # a space in the middle
    assert agreement["invoice_number"] == "agree"
    assert agreement["invoice_date"] == "agree"  # 14-08 vs 14/08
    assert agreement["place_of_supply"] == "agree"
    assert agreement["total"] == "agree" and agreement["taxable_value"] == "agree"
    assert agreement["line_items[0].gst_rate"] == "agree"  # 12% vs 12
    assert agreement["tax_lines[0].rate"] == "agree"  # 6 vs 6.0
    assert "differ" not in agreement.values()


def test_a_different_value_differs_and_an_unseen_value_is_missing():
    b = reading_b(total="1,210.00", vendor_gstin=None)
    _, agreement = compare_and_fill(extraction(), b, DOC)
    assert agreement["total"] == "differ"
    assert agreement["vendor_gstin"] == "missing"  # A has it, B did not see it


def test_round_off_none_and_zero_are_the_same():
    _, agreement = compare_and_fill(extraction(), reading_b(round_off="0.00"), DOC)
    assert agreement["round_off"] == "agree"  # A printed none, B read 0.00
    _, agreement = compare_and_fill(extraction(), reading_b(round_off="1.00"), DOC)
    assert agreement["round_off"] == "differ"


def test_rows_that_exist_in_one_reading_only_are_one_table_level_difference():
    b = reading_b(line_items=[], tax_lines=[])
    _, agreement = compare_and_fill(extraction(), b, DOC)
    assert agreement["line_items"] == "differ" and agreement["tax_lines"] == "differ"
    assert not any(p.startswith("line_items[") for p in agreement)


def test_a_gap_is_filled_only_when_the_value_is_in_the_page_words():
    doc = document("Buyer: Shree Ganesh Traders", "Total 1,120.00")
    a = extraction(buyer_name=ev(None))
    filled, agreement = compare_and_fill(a, reading_b(buyer_name="Shree Ganesh Traders"), doc)
    assert agreement["buyer_name"] == "filled"
    assert filled.buyer_name.value == "Shree Ganesh Traders"
    assert filled.buyer_name.evidence == ["w2", "w3", "w4"]
    assert a.buyer_name.value is None  # the input is not changed

    invented = reading_b(buyer_name="Totally Invented Pvt Ltd")
    kept, agreement = compare_and_fill(a, invented, doc)
    assert agreement["buyer_name"] == "missing" and kept.buyer_name.value is None


def test_the_value_of_reading_a_is_never_replaced():
    b = reading_b(total="9,999.00")
    merged, agreement = compare_and_fill(extraction(), b, document("9,999.00"))
    assert agreement["total"] == "differ" and merged.total.value == "1,120.00"


def test_locate_value_finds_whole_values_across_words_and_never_inside_a_longer_one():
    doc = document("GSTIN: 27QWRCA73 10M1ZK", "Total 11,200.00")
    assert locate_value(doc, "27QWRCA7310M1ZK") == ["w2", "w3"]
    assert locate_value(doc, "1,200.00") is None  # inside 11,200.00 only
    assert locate_value(doc, "11,200.00") == ["w5"]
    assert locate_value(doc, "") is None and locate_value(doc, "absent") is None


def grounded(conf: float = 0.9) -> dict[str, GroundedField]:
    return {
        "total": GroundedField(raw="1", grounding="grounded", confidence=conf),
        "vendor_name": GroundedField(raw="x", grounding="grounded", confidence=conf),
        "invoice_number": GroundedField(raw="y", grounding="grounded", confidence=0.3),
    }


def test_differing_or_single_sourced_values_are_capped_at_half_and_nothing_is_raised():
    agreement = {"total": "differ", "vendor_name": "agree", "invoice_number": "filled"}
    capped = apply_agreement_caps(grounded(), agreement)
    assert capped["total"].confidence == 0.5
    assert capped["vendor_name"].confidence == 0.9
    assert capped["invoice_number"].confidence == 0.3  # already lower than the cap
    assert apply_agreement_caps(grounded(), None) == grounded()
    assert apply_agreement_caps(grounded(), {"total": "missing"})["total"].confidence == 0.9


def test_a_warning_for_each_differing_field_only():
    issues = readings_disagree_issues(
        {"total": "differ", "vendor_name": "agree", "line_items": "differ", "gstin": "missing"}
    )
    assert [i.field for i in issues] == ["total", "line_items"]
    assert all(i.code == IssueCode.READINGS_DISAGREE for i in issues)
    assert all(i.severity == Severity.WARNING for i in issues)
    assert readings_disagree_issues(None) == [] and readings_disagree_issues({}) == []


def test_a_quantity_with_a_unit_equals_the_bare_number_but_not_another_number():
    a = extraction(
        line_items=[
            ExtractedLineItem(
                description=ev("Paper", "w1"),
                hsn_sac=ev(None),
                quantity=ev("20 ream", "w2"),
                rate=ev(None),
                gst_rate=ev(None),
                taxable_amount=ev(None),
            )
        ]
    )
    same = reading_b(line_items=[SecondLineItem(description="Paper", quantity="20")])
    other = reading_b(line_items=[SecondLineItem(description="Paper", quantity="2")])
    assert compare_and_fill(a, same, DOC)[1]["line_items[0].quantity"] == "agree"
    assert compare_and_fill(a, other, DOC)[1]["line_items[0].quantity"] == "differ"
