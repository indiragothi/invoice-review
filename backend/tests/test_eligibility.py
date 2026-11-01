from app.correction_email.eligibility import SUPPLIER_FIXABLE, eligible_issues, is_supplier_fixable
from app.schemas.issues import IssueCode, make_issue

NOT_ELIGIBLE = {
    IssueCode.UNGROUNDED_REQUIRED_FIELD,
    IssueCode.AMBIGUOUS_DATE,
    IssueCode.LOW_CONFIDENCE_FIELD,
    IssueCode.READINGS_DISAGREE,
    IssueCode.DUPLICATE_INVOICE,
    IssueCode.DUPLICATE_RECEIPT,
    IssueCode.DUPLICATE_FILE,
}


def test_the_policy_lists_fourteen_supplier_fixable_codes():
    assert len(SUPPLIER_FIXABLE) == 14


def test_our_own_problems_are_never_eligible():
    for code in NOT_ELIGIBLE:
        assert not is_supplier_fixable(code), code
    assert not NOT_ELIGIBLE & SUPPLIER_FIXABLE


def test_supplier_mistakes_are_eligible_whatever_their_severity():
    assert is_supplier_fixable(IssueCode.INVALID_VENDOR_GSTIN)  # blocking
    assert is_supplier_fixable(IssueCode.MISSING_HSN_SAC)  # warning
    assert is_supplier_fixable(IssueCode.AMOUNT_IN_WORDS_MISMATCH)  # warning


def test_eligible_issues_keeps_only_those_and_their_order():
    issues = [
        make_issue(IssueCode.LOW_CONFIDENCE_FIELD, "a"),
        make_issue(IssueCode.TOTAL_MISMATCH, "b"),
        make_issue(IssueCode.DUPLICATE_FILE, "c"),
        make_issue(IssueCode.MISSING_HSN_SAC, "d"),
    ]
    assert [i.message for i in eligible_issues(issues)] == ["b", "d"]
    assert eligible_issues([]) == []
