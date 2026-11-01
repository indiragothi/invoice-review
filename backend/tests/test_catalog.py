from app.accounting.catalog import LEDGERS, LEDGERS_BY_CODE, catalog_for_prompt, checked_ledger_code


def test_catalog_has_the_thirteen_policy_ledgers_with_unique_codes():
    assert len(LEDGERS) == 13
    assert len(LEDGERS_BY_CODE) == 13
    assert LEDGERS_BY_CODE["6130"].name == "Fuel and vehicle running"
    assert LEDGERS_BY_CODE["6190"].name == "Miscellaneous expenses"


def test_checked_ledger_code_accepts_only_catalog_codes():
    assert checked_ledger_code("6130") == "6130"
    assert checked_ledger_code(" 6100 ") == "6100"
    for bad in ("9999", "6130.0", "Rent", "", None):
        assert checked_ledger_code(bad) is None


def test_prompt_catalog_lists_every_code_once():
    lines = catalog_for_prompt().splitlines()
    assert len(lines) == 13
    assert lines[0].startswith("1500 | Fixed assets")
