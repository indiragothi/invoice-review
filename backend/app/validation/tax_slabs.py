"""GST rate slabs by date (decision D8). Data, not code branches.

VERIFY these tables against the official CBIC rate notifications before relying on them
(docs/policy-rules.md). A rate outside the table is only a warning, because transition-period
bills and special items (precious stones, some services) are common.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class SlabTable:
    effective_from: date
    rates: frozenset[Decimal]  # percent


def _rates(*values: str) -> frozenset[Decimal]:
    return frozenset(Decimal(v) for v in values)


# Oldest first. Dates before the first entry use the first table.
SLAB_TABLES: tuple[SlabTable, ...] = (
    SlabTable(date(2017, 7, 1), _rates("0", "0.25", "1.5", "3", "5", "12", "18", "28")),
    # GST rate rationalisation, effective 22 September 2025: main slabs 0 / 5 / 18 plus 40.
    SlabTable(date(2025, 9, 22), _rates("0", "0.25", "3", "5", "18", "40")),
)


def slabs_on(on: date) -> frozenset[Decimal]:
    table = SLAB_TABLES[0]
    for candidate in SLAB_TABLES:
        if candidate.effective_from <= on:
            table = candidate
    return table.rates


def is_valid_slab(rate: Decimal, on: date) -> bool:
    return rate in slabs_on(on)
