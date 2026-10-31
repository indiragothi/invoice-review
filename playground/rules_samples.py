"""Experiment: ground, normalise and review every cached extraction. Offline, no API calls.

For each sample it runs the whole M2 validation (`review_document`) and compares the blocking
codes and the status with manifest.json (`expected_errors`, `expected_status`), then checks the
duplicate keys. Run from backend/ after `extract_samples.py all` has filled the cache:

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
from app.schemas.extraction import Extraction  # noqa: E402
from app.schemas.issues import Severity  # noqa: E402
from app.validation.duplicates import invoice_key, receipt_key  # noqa: E402
from app.validation.review import review_document  # noqa: E402

CACHE = Path(__file__).resolve().parent / "output" / "extract"
TODAY = date(2026, 10, 31)  # the samples are dated Aug - Oct 2026


def main() -> None:
    manifest = json.loads((APP_CONFIG.samples_dir / "manifest.json").read_text(encoding="utf-8"))
    loaded = {}
    for entry in manifest["documents"]:
        path = APP_CONFIG.samples_dir / entry["file"]
        cached = json.loads((CACHE / f"{path.stem}.json").read_text(encoding="utf-8"))
        extraction = Extraction.model_validate(cached["extraction"])
        document = normalise_extraction(extraction)
        fields = ground_extraction(extraction, read_document(path.read_bytes()).document)
        loaded[entry["file"]] = (entry, document, fields)

    agree = 0
    for file, (entry, document, fields) in loaded.items():
        client = CLIENTS_BY_ID[entry["client"]]
        result = review_document(document, fields, client, TODAY)

        errors = {i.code.value for i in result.issues if i.severity == Severity.ERROR}
        warnings = sorted(i.code.value for i in result.issues if i.severity == Severity.WARNING)
        ok = errors == set(entry["expected_errors"]) and result.status == entry["expected_status"]
        agree += ok
        verdict = "OK " if ok else "BAD"
        print(f"{verdict} {file}: {result.status} (want {entry['expected_status']})")
        print(f"      errors {sorted(errors)} want {sorted(entry['expected_errors'])}")
        if warnings:
            print(f"      warnings {warnings}")
        for issue in result.issues:
            if issue.suggestion:
                print(f"      {issue.code.value}: {issue.message}")
    print(f"\nAGREE {agree}/{len(loaded)} documents (errors and status)")
    check_duplicates(loaded)


def check_duplicates(loaded: dict) -> None:
    """Keys must be unique across the samples; uploading any sample again must flag exactly it."""
    keys = {
        file: invoice_key(doc) if doc.document_type == "invoice" else receipt_key(doc)
        for file, (_, doc, _) in loaded.items()
    }
    unique = len(set(keys.values())) == len(keys) and None not in keys.values()
    flagged = 0
    for file, (entry, doc, fields) in loaded.items():
        same_kind = {f: k for f, k in keys.items() if type(k) is type(keys[file])}
        result = review_document(
            doc, fields, CLIENTS_BY_ID[entry["client"]], TODAY, existing=same_kind
        )
        code = "duplicate_invoice" if doc.document_type == "invoice" else "duplicate_receipt"
        hits = [i for i in result.issues if i.code.value == code]
        flagged += len(hits) == 1 and file in hits[0].message
    print(
        f"DUPLICATES keys unique: {unique}; re-upload flagged against itself: {flagged}/{len(keys)}"
    )


if __name__ == "__main__":
    main()
