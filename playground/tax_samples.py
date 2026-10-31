"""Experiment: run the tax checks on the cached extractions and compare with manifest.json.

Offline. Only the three tax-related error codes are compared. Run from backend/:

    uv run --locked --no-sync python ../playground/tax_samples.py
"""

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.clients import CLIENTS_BY_ID  # noqa: E402
from app.config import APP_CONFIG  # noqa: E402
from app.normalisation.assemble import normalise_extraction  # noqa: E402
from app.schemas.documents import Invoice  # noqa: E402
from app.schemas.extraction import Extraction  # noqa: E402
from app.validation import tax  # noqa: E402

CACHE = Path(__file__).resolve().parent / "output" / "extract"
TAX_CODES = {"total_mismatch", "line_items_sum_mismatch", "tax_split_inconsistent"}


def main() -> None:
    manifest = json.loads((APP_CONFIG.samples_dir / "manifest.json").read_text(encoding="utf-8"))
    agree = 0
    for entry in manifest["documents"]:
        stem = Path(entry["file"]).stem
        cached = json.loads((CACHE / f"{stem}.json").read_text(encoding="utf-8"))
        doc = normalise_extraction(Extraction.model_validate(cached["extraction"]))
        totals = tax.tax_totals(doc.tax_lines)
        found: set[str] = set()
        notes: list[str] = []

        if isinstance(doc, Invoice):
            client = CLIENTS_BY_ID[entry["client"]]
            supply = tax.supply_type(
                doc.vendor_gstin, doc.place_of_supply_code, doc.buyer_gstin, client.state_code
            )
            problem = tax.tax_split_problem(supply, totals) if supply else None
            if problem:
                found.add("tax_split_inconsistent")
            computed = tax.invoice_computed_total(doc.taxable_value, totals, doc.round_off)
            if computed is not None and doc.total is not None and tax.differs(computed, doc.total):
                found.add("total_mismatch")
            lines = tax.line_items_sum(doc.line_items)
            if lines is not None and doc.taxable_value is not None:
                if tax.differs(lines, doc.taxable_value):
                    found.add("line_items_sum_mismatch")
            notes.append(f"supply={supply} split={problem} computed={computed} total={doc.total}")
        else:
            computed = tax.receipt_computed_total(doc.line_items, totals, doc.round_off)
            if computed is not None and doc.total is not None and tax.differs(computed, doc.total):
                found.add("line_items_sum_mismatch")
            notes.append(f"computed={computed} total={doc.total}")

        expected = set(entry["expected_errors"]) & TAX_CODES
        ok = found == expected
        agree += ok
        verdict = "OK " if ok else "BAD"
        print(f"{verdict} {entry['file']}: found {sorted(found)} want {sorted(expected)}")
        print(f"      {' '.join(notes)}")
    print(f"\nAGREE {agree}/{len(manifest['documents'])}")


if __name__ == "__main__":
    main()
