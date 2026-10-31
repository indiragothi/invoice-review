"""Experiment: compare two prompt versions on the cached dev-split extractions. Offline.

Shows, per document, how many fields match the manifest, how many values are still ungrounded
after grounding (with re-pointing), and the review status / blocking codes. Test documents are
never included: prompts are tuned on the dev split only (docs/evaluation.md).

    uv run --locked --no-sync python ../playground/compare_prompts.py extract_v1 extract_v2
"""

import json
import sys
from datetime import date
from pathlib import Path

PLAYGROUND = Path(__file__).resolve().parent
BACKEND = PLAYGROUND.parent / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(PLAYGROUND))

from extract_samples import compare  # noqa: E402

from app.clients import CLIENTS_BY_ID  # noqa: E402
from app.config import APP_CONFIG  # noqa: E402
from app.normalisation.assemble import normalise_extraction  # noqa: E402
from app.pipeline.grounding import ground_extraction  # noqa: E402
from app.reader import read_document  # noqa: E402
from app.schemas.extraction import Extraction  # noqa: E402
from app.schemas.issues import Severity  # noqa: E402
from app.validation.review import review_document  # noqa: E402

TODAY = date(2026, 10, 31)


def cache_dir(version: str) -> Path:
    return PLAYGROUND / "output" / ("extract" if version == "extract_v1" else version)


def measure(version: str, entry: dict) -> dict:
    path = APP_CONFIG.samples_dir / entry["file"]
    cached = json.loads((cache_dir(version) / f"{path.stem}.json").read_text(encoding="utf-8"))
    extraction = Extraction.model_validate(cached["extraction"])
    read = read_document(path.read_bytes()).document
    fields = ground_extraction(extraction, read)
    right, wrong = compare(extraction, entry["fields"])
    document = normalise_extraction(extraction)
    result = review_document(document, fields, CLIENTS_BY_ID[entry["client"]], TODAY)
    return {
        "fields": f"{len(right)}/{len(right) + len(wrong)}",
        "wrong": wrong,
        "ungrounded": sum(f.grounding == "ungrounded" for f in fields.values()),
        "lines": len(extraction.line_items),
        "status": result.status,
        "errors": sorted(i.code.value for i in result.issues if i.severity == Severity.ERROR),
        "warnings": sorted(i.code.value for i in result.issues if i.severity == Severity.WARNING),
        "vendor": extraction.vendor_name.value,
        "tokens": cached["call"]["input_tokens"] + cached["call"]["output_tokens"],
    }


def main() -> None:
    old, new = sys.argv[1], sys.argv[2]
    manifest = json.loads((APP_CONFIG.samples_dir / "manifest.json").read_text(encoding="utf-8"))
    for entry in (d for d in manifest["documents"] if d["split"] == "dev"):
        a, b = measure(old, entry), measure(new, entry)
        print(f"\n{entry['file']}  (want {entry['expected_status']}, {entry['expected_errors']})")
        for key in ("fields", "ungrounded", "lines", "status", "errors", "warnings", "tokens"):
            flag = "" if a[key] == b[key] else "   <-- differs"
            print(f"   {key:<11} {old}: {a[key]!s:<28} {new}: {b[key]!s}{flag}")
        if a["vendor"] != b["vendor"]:
            print(f"   vendor      {old}: {a['vendor']!r}  {new}: {b['vendor']!r}")
        for line in b["wrong"]:
            print(f"   {new} wrong: {line}")


if __name__ == "__main__":
    main()
