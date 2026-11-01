"""Experiment: run upload intake on the 12 samples and on a few bad files. Offline.

uv run --locked --no-sync python ../playground/intake_samples.py
"""

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import APP_CONFIG  # noqa: E402
from app.documents.intake import IntakeError, check_upload  # noqa: E402


def main() -> None:
    manifest = json.loads((APP_CONFIG.samples_dir / "manifest.json").read_text(encoding="utf-8"))
    ok = 0
    for entry in manifest["documents"]:
        accepted = check_upload((APP_CONFIG.samples_dir / entry["file"]).read_bytes())
        match = accepted.page_count == entry["pages"]
        ok += match
        print(
            f"{'OK ' if match else 'BAD'} {entry['file']}: {accepted.content_type}, "
            f"{accepted.page_count} page(s) (manifest {entry['pages']})"
        )
    print(f"\nACCEPTED {ok}/{len(manifest['documents'])} with the right page count")

    bad = {
        "renamed .exe": b"MZ\x90\x00" + b"\x00" * 100,
        "6 MB file": b"%PDF-" + b"0" * (APP_CONFIG.max_upload_bytes + 1),
        "damaged PDF": b"%PDF-1.7 not really",
    }
    for label, data in bad.items():
        try:
            check_upload(data)
            print(f"BAD {label}: accepted")
        except IntakeError as error:
            print(f"OK  {label}: {error.status_code} {error.message}")


if __name__ == "__main__":
    main()
