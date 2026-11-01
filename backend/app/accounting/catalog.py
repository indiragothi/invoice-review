"""The fixed ledger catalog (docs/policy-rules.md). Code is the authority, not the model.

A model may only pick a code from this list; `checked_ledger_code` turns anything else into
None. Approval needs a valid selected ledger (enforced by the service).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Ledger:
    code: str
    name: str
    typical: str


LEDGERS: tuple[Ledger, ...] = (
    Ledger("1500", "Fixed assets", "Computers, machinery, furniture"),
    Ledger("5100", "Purchase of goods", "Stock-in-trade bought for resale"),
    Ledger("5110", "Raw material and consumables", "Inputs used in production / service"),
    Ledger("6100", "Rent", "Shop, office, warehouse rent"),
    Ledger("6110", "Electricity and water", "Utility bills"),
    Ledger("6120", "Telephone and internet", "Mobile, broadband"),
    Ledger("6130", "Fuel and vehicle running", "Petrol, diesel, vehicle service"),
    Ledger("6140", "Repairs and maintenance", "Building, equipment repairs"),
    Ledger("6150", "Printing and stationery", "Office supplies"),
    Ledger("6160", "Professional and legal fees", "CA, lawyer, consultant"),
    Ledger("6170", "Travel and conveyance", "Taxi, train, flight, hotel"),
    Ledger("6180", "Staff welfare and food", "Meals, refreshments"),
    Ledger("6190", "Miscellaneous expenses", "Anything else"),
)

LEDGERS_BY_CODE: dict[str, Ledger] = {ledger.code: ledger for ledger in LEDGERS}


def checked_ledger_code(code: str | None) -> str | None:
    """The code if it is in the catalog (surrounding spaces ignored), otherwise None."""
    cleaned = (code or "").strip()
    return cleaned if cleaned in LEDGERS_BY_CODE else None


def catalog_for_prompt() -> str:
    """One line per ledger for the suggestion prompt: `6130 | Fuel and vehicle running | ...`."""
    return "\n".join(f"{x.code} | {x.name} | {x.typical}" for x in LEDGERS)
