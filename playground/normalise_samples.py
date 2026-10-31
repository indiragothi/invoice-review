"""Experiment: normalise the cached extractions and compare with manifest.json. Offline.

Run from backend/ after `extract_samples.py all` has filled the cache:

    uv run --locked --no-sync python ../playground/normalise_samples.py
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import APP_CONFIG  # noqa: E402
from app.normalisation.assemble import normalise_extraction  # noqa: E402
from app.schemas.documents import Invoice  # noqa: E402
from app.schemas.extraction import Extraction  # noqa: E402

CACHE = Path(__file__).resolve().parent / "output" / "extract"


def tax_total(doc: Invoice, head: str) -> Decimal:
    return sum((t.amount or Decimal(0) for t in doc.tax_lines if t.head == head), Decimal(0))


def main() -> None:
    manifest = json.loads((APP_CONFIG.samples_dir / "manifest.json").read_text(encoding="utf-8"))
    right = total = 0
    for entry in manifest["documents"]:
        stem = Path(entry["file"]).stem
        cached = json.loads((CACHE / f"{stem}.json").read_text(encoding="utf-8"))
        doc = normalise_extraction(Extraction.model_validate(cached["extraction"]))
        want = entry["fields"]
        checks: dict[str, tuple[object, object]] = {
            "total": (doc.total, Decimal(want["total"])),
            "cgst": (tax_total(doc, "CGST"), Decimal(want["cgst"])) if "cgst" in want else (0, 0),
            "sgst": (tax_total(doc, "SGST"), Decimal(want["sgst"])) if "sgst" in want else (0, 0),
            "igst": (tax_total(doc, "IGST"), Decimal(want["igst"])) if "igst" in want else (0, 0),
        }
        date_field = doc.invoice_date if isinstance(doc, Invoice) else doc.receipt_date
        if "invoice_date" in want:
            checks["date"] = (
                date_field.value.isoformat() if date_field.value else None,
                want["invoice_date"],
            )
        if isinstance(doc, Invoice):
            for name in ("taxable_value", "vendor_gstin", "buyer_gstin"):
                if name in want:
                    checks[name] = (
                        getattr(doc, name),
                        Decimal(want[name]) if name == "taxable_value" else want[name],
                    )
            if "place_of_supply" in want:
                checks["place_of_supply"] = (doc.place_of_supply_code, want["place_of_supply"])
        bad = {k: v for k, v in checks.items() if v[0] != v[1]}
        right += len(checks) - len(bad)
        total += len(checks)
        flag = "ambiguous date! " if date_field.ambiguous else ""
        print(f"{entry['file']}: {len(checks) - len(bad)}/{len(checks)} {flag}{bad or ''}")
    print(f"\nTOTAL {right}/{total}")


if __name__ == "__main__":
    main()
