import pytest

from app.clients import CLIENTS
from app.validation.gstin import check_gstin, suggest_fix

CLIENT = "23QXGPS4821K1ZU"
SAMPLE_05_INVALID = "23QMRPW2963E1ZE"  # check character deliberately wrong
SAMPLE_05_FIXED = "23QMRPW2963E1Z7"


@pytest.mark.parametrize("gstin", [c.gstin for c in CLIENTS] + ["27AAPFU0939F1ZV"])
def test_valid_gstins(gstin):
    result = check_gstin(gstin)
    assert result.valid
    assert result.problem is None
    assert result.suggestion is None


def test_wrong_check_character_is_a_checksum_problem():
    result = check_gstin("27AAPFU0939F1ZO")
    assert not result.valid
    assert result.problem == "checksum"


@pytest.mark.parametrize("gstin", ["", "27AAPFU0939F1Z", "27AAPFU0939F1ZVV"])
def test_wrong_length(gstin):
    assert check_gstin(gstin).problem == "length"
    assert check_gstin(gstin).suggestion is None


def test_all_digits_is_a_format_problem():
    assert check_gstin("369296450896540").problem == "format"


def test_fourteenth_character_must_be_z():
    assert check_gstin("27AAPFU0939F1AA").problem == "format"


def test_unknown_state_code():
    assert check_gstin("00AAPFU0939F1ZV").problem == "state"


def test_pan_part_must_be_valid():
    # 4th PAN letter "X" is not a holder type.
    assert check_gstin("27AAPXU0939F1ZV").problem == "pan"


@pytest.mark.parametrize("code", ["38", "97", "99"])
def test_state_codes_missing_from_stdnum_are_accepted_by_state_check(code):
    # Not checksum-valid here, but the failure must be the checksum, not the state.
    assert check_gstin(f"{code}AAPFU0939F1ZV").problem != "state"


def test_ocr_confusion_gets_a_suggestion_that_passes():
    swapped_s = "23QXGP54821K1ZU"  # S read as 5
    swapped_one = "23QXGPS4821KIZU"  # 1 read as I
    for bad in (swapped_s, swapped_one):
        result = check_gstin(bad)
        assert not result.valid
        assert result.suggestion == CLIENT
        assert check_gstin(result.suggestion).valid


def test_checksum_typo_suggests_the_check_character():
    result = check_gstin(SAMPLE_05_INVALID)
    assert result.problem == "checksum"
    assert result.suggestion == SAMPLE_05_FIXED
    assert check_gstin(SAMPLE_05_FIXED).valid


def test_no_suggestion_for_a_structurally_broken_number():
    assert suggest_fix("00AAPFU0939F1ZV") is None
    assert suggest_fix("27AAPFU0939F1AA") is None


def test_suggestion_is_never_applied_to_a_valid_number():
    assert check_gstin(CLIENT).suggestion is None
