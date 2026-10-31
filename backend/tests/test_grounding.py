from app.pipeline.grounding import ground_extraction, ground_value
from app.reader.schemas import Page, ReadDocument, Word
from app.schemas.extraction import Evidenced, Extraction


def word(i: int, text: str, x: int, y: int = 10, *, line: int | None = None, conf: float = 1.0):
    return Word(
        id=f"w{i}", page=1, line=line or i, text=text, box=(x, y, x + 40, y + 10), confidence=conf
    )


def doc(words: list[Word], source: str = "pdf_text") -> ReadDocument:
    return ReadDocument(
        content_type="application/pdf",
        pages=[Page(number=1, width=1000, height=1000, text_source=source)],
        words=words,
    )


def ev(value: str | None, *ids: str) -> Evidenced:
    return Evidenced(value=value, evidence=list(ids))


def test_value_in_cited_words_is_grounded_with_union_box():
    d = doc([word(1, "Shree", 0), word(2, "Ganesh", 50), word(3, "Traders", 100)])
    g = ground_value(ev("Shree Ganesh", "w1", "w2"), d)
    assert g.grounding == "grounded"
    assert g.evidence == ["w1", "w2"]
    assert g.box == (0, 10, 90, 20)
    assert g.confidence == 1.0


def test_extra_cited_words_are_trimmed_to_the_smallest_run():
    d = doc([word(1, "Invoice", 0), word(2, "No:", 50), word(3, "INV-7", 100)])
    g = ground_value(ev("INV-7", "w1", "w2", "w3"), d)
    assert g.evidence == ["w3"]
    assert g.box == (100, 10, 140, 20)


def test_null_value_is_missing():
    g = ground_value(ev(None), doc([word(1, "x", 0)]))
    assert g.grounding == "missing"
    assert g.box is None
    assert g.confidence == 0.0


def test_value_not_in_the_document_is_ungrounded():
    d = doc([word(1, "Total", 0), word(2, "1,000.00", 50)])
    g = ground_value(ev("9,999.00", "w2"), d)
    assert g.grounding == "ungrounded"
    assert g.box is None
    assert g.confidence == 0.0


def test_unknown_evidence_id_is_ungrounded():
    g = ground_value(ev("1,000.00", "w99"), doc([word(1, "1,000.00", 0)]))
    assert g.grounding == "ungrounded"


def test_off_by_one_citation_is_repointed_along_the_row():
    # Table cells sit on different `line` numbers but the same y: still one row.
    d = doc(
        [
            word(1, "1006", 0, line=1),
            word(2, "6", 50, line=2),
            word(3, "pcs", 100, line=2),
            word(4, "560.00", 150, line=3),
        ]
    )
    g = ground_value(ev("1006", "w3"), d)
    assert g.grounding == "grounded"
    assert g.evidence == ["w1"]


def test_repoint_picks_the_match_nearest_the_cited_word():
    d = doc([word(1, "18", 0), word(2, "x", 50), word(3, "y", 100), word(4, "18", 150)])
    g = ground_value(ev("18", "w3"), d)
    assert g.evidence == ["w4"]


def test_repoint_needs_a_whole_word_never_a_fragment():
    # "9" sits inside "1,980" on the same row: must not be accepted.
    d = doc([word(1, "1,980", 0), word(2, "pcs", 50)])
    g = ground_value(ev("9", "w2"), d)
    assert g.grounding == "ungrounded"


def test_citation_in_next_row_finds_value_a_word_before():
    d = doc([word(1, "3,360.00", 0, y=10), word(2, "19", 0, y=100), word(3, "Wheat", 50, y=100)])
    g = ground_value(ev("3,360.00", "w2"), d)
    assert g.grounding == "grounded"
    assert g.evidence == ["w1"]


def test_spaces_and_case_are_ignored_for_ocr_text():
    d = doc([word(1, "RestaurantPvtLtd", 0, conf=0.9)], source="ocr")
    g = ground_value(ev("Restaurant Pvt Ltd", "w1"), d)
    assert g.grounding == "grounded"
    assert g.source == "ocr"


def test_ocr_confidence_is_the_mean_of_the_evidence_words():
    d = doc([word(1, "A", 0, conf=0.9), word(2, "B", 50, conf=0.7)], source="ocr")
    g = ground_value(ev("A B", "w1", "w2"), d)
    assert abs(g.confidence - 0.8) < 1e-9


def test_ground_extraction_keys_cover_line_items_and_tax_lines():
    d = doc([word(1, "Acme", 0), word(2, "1000", 50), word(3, "9", 100), word(4, "90", 150)])
    empty = ev(None)
    extraction = Extraction.model_validate(
        {
            "document_type": "invoice",
            "classification_reason": "x",
            "vendor_name": ev("Acme", "w1").model_dump(),
            **{
                k: empty.model_dump()
                for k in (
                    "vendor_gstin buyer_name buyer_gstin invoice_number invoice_date "
                    "place_of_supply round_off total amount_in_words"
                ).split()
            },
            "taxable_value": ev("1000", "w2").model_dump(),
            "line_items": [],
            "tax_lines": [
                {
                    "head": "CGST",
                    "rate": ev("9", "w3").model_dump(),
                    "amount": ev("90", "w4").model_dump(),
                }
            ],
        }
    )
    grounded = ground_extraction(extraction, d)
    assert grounded["vendor_name"].grounding == "grounded"
    assert grounded["taxable_value"].evidence == ["w2"]
    assert grounded["tax_lines[0].amount"].grounding == "grounded"
    assert grounded["total"].grounding == "missing"
