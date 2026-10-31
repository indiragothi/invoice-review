"""Experiment: run grounding on the cached extractions of all samples. Offline: no API calls.

Run from backend/ after `extract_samples.py all` has filled the cache:

    uv run --locked --no-sync python ../playground/ground_samples.py
"""

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import APP_CONFIG  # noqa: E402
from app.pipeline.grounding import _evidenced_fields, ground_extraction  # noqa: E402
from app.reader import read_document  # noqa: E402
from app.schemas.extraction import Extraction  # noqa: E402

CACHE = Path(__file__).resolve().parent / "output" / "extract"


def main() -> None:
    manifest = json.loads((APP_CONFIG.samples_dir / "manifest.json").read_text(encoding="utf-8"))
    total = {"grounded": 0, "ungrounded": 0, "missing": 0, "repointed": 0}
    for entry in manifest["documents"]:
        path = APP_CONFIG.samples_dir / entry["file"]
        cached = json.loads((CACHE / f"{path.stem}.json").read_text(encoding="utf-8"))
        extraction = Extraction.model_validate(cached["extraction"])
        read = read_document(path.read_bytes()).document
        grounded = ground_extraction(extraction, read)

        cited = {name: value.evidence for name, value in _evidenced_fields(extraction)}
        counts = {"grounded": 0, "ungrounded": 0, "missing": 0}
        notes = []
        for name, field in grounded.items():
            counts[field.grounding] += 1
            if field.grounding == "ungrounded":
                notes.append(f"   UNGROUNDED {name}={field.raw!r} cited {field.evidence}")
            elif field.grounding == "grounded" and name in cited and set(field.evidence) - set(
                cited[name]
            ):
                total["repointed"] += 1
                moved = f"{cited[name]} -> {field.evidence}"
                notes.append(f"   re-pointed {name}={field.raw!r}: {moved}")
        for key in counts:
            total[key] += counts[key]
        print(f"{path.name}: {counts}")
        for note in notes:
            print(note)
    print(f"\nTOTAL {total}")


if __name__ == "__main__":
    main()
