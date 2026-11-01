from app.schemas.issues import IssueCode, make_issue
from app.validation.approval import approval_blockers, rejection_blockers

ERROR = make_issue(IssueCode.TOTAL_MISMATCH, "total differs")
WARNING = make_issue(IssueCode.MISSING_HSN_SAC, "no HSN")


def test_a_ready_record_with_a_ledger_can_be_approved_even_with_warnings():
    assert approval_blockers("ready", [WARNING], "6130") == []


def test_no_ledger_or_a_code_outside_the_catalog_blocks_approval():
    for code in (None, "", "9999", "Rent"):
        assert approval_blockers("ready", [], code) == ["Select a ledger before approving."]


def test_a_blocking_error_blocks_approval_and_is_named():
    blockers = approval_blockers("ready", [ERROR, WARNING], "6130")
    assert blockers == ["Open blocking errors: total_mismatch."]


def test_needs_review_never_becomes_approved_even_with_a_ledger():
    blockers = approval_blockers("needs_review", [ERROR], "6130")
    assert len(blockers) == 2 and "needs_review" in blockers[0]


def test_other_states_cannot_be_approved():
    for status in ("processing", "failed"):
        assert approval_blockers(status, [], "6130")


def test_a_decided_record_is_locked_for_both_decisions():
    for status in ("approved", "rejected"):
        assert "locked" in approval_blockers(status, [], "6130")[0]
        assert "locked" in rejection_blockers(status)[0]


def test_ready_and_needs_review_can_be_rejected_but_failed_cannot():
    assert rejection_blockers("ready") == []
    assert rejection_blockers("needs_review") == []
    assert rejection_blockers("failed") and rejection_blockers("processing")
