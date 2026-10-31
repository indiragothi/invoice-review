"""Experiment: ground, normalise and run the invoice rules on the cached extractions.

Offline. Compares the blocking codes the rules find (header + amount rules) with the
manifest.json `expected_errors`, only for the codes implemented so far. Run from backend/:

    uv run --locked --no-sync python ../playground/rules_samples.py
"""

import json
import sys
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.clients import CLIENTS_BY_ID  # noqa: E402
from app.config import APP_CONFIG  # noqa: E402
from app.normalisation.assemble import normalise_extraction  # noqa: E402
from app.pipeline.grounding import ground_extraction  # noqa: E402
from app.reader import read_document  # noqa: E402
from app.schemas.documents import Invoice  # noqa: E402
from app.schemas.extraction import Extraction  # noqa: E402
from app.schemas.issues import Severity  # noqa: E402
from app.validation.invoice import validate_invoice  # noqa: E402

CACHE = Path(__file__).resolve().parent / "output" / "extract"
TODAY = date(2026, 10, 31)  # the samples are dated Aug - Oct 2026
IMPLEMENTED = {
    "missing_vendor_name",
    "missing_invoice_number",
    "missing_invoice_date",
    "invalid_date",
    "ambiguous_date",
    "missing_total",
    "missing_vendor_gstin",
    "invalid_vendor_gstin",
    "invalid_buyer_gstin",
    "buyer_not_client",
    "ungrounded_required_field",
    "line_items_sum_mismatch",
    "total_mismatch",
    "tax_split_inconsistent",
}


def main() -> None:
    manifest = json.loads((APP_CONFIG.samples_dir / "manifest.json").read_text(encoding="utf-8"))
    agree = checked = 0
    for entry in manifest["documents"]:
        path = APP_CONFIG.samples_dir / entry["file"]
        cached = json.loads((CACHE / f"{path.stem}.json").read_text(encoding="utf-8"))
        extraction = Extraction.model_validate(cached["extraction"])
        document = normalise_extraction(extraction)
        if not isinstance(document, Invoice):
            continue
        fields = ground_extraction(extraction, read_document(path.read_bytes()).document)
        client = CLIENTS_BY_ID[entry["client"]]
        issues = validate_invoice(document, fields, client, TODAY)

        found = {i.code.value for i in issues if i.severity == Severity.ERROR}
        expected = set(entry["expected_errors"]) & IMPLEMENTED
        ok = found == expected
        agree += ok
        checked += 1
        warnings = sorted(i.code.value for i in issues if i.severity == Severity.WARNING)
        verdict = "OK " if ok else "BAD"
        print(f"{verdict} {entry['file']}: errors {sorted(found)} want {sorted(expected)}")
        if warnings:
            print(f"      warnings {warnings}")
        for issue in issues:
            if issue.suggestion:
                print(f"      {issue.code.value}: {issue.message}")
    print(f"\nAGREE {agree}/{checked} invoices")


if __name__ == "__main__":
    main()
