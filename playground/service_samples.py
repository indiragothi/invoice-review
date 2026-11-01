"""Experiment: upload the 12 samples through the document service. Offline, no API calls.

Uses a throw-away database and uploads folder in playground/output/service_check/, cached model
answers, and checks: status vs manifest, the stored file, the pipeline run record, a re-upload
(file + content duplicates), a rejected file (nothing stored), an unknown client, a provider
failure (saved as `failed`, then retried to success), and a ledger failure (kept, no code).
Run from backend/:

    uv run --locked --no-sync python ../playground/service_samples.py
"""

import json
import shutil
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline_samples import TODAY, cached_extractor, cached_ledger_suggester  # noqa: E402

from app.config import APP_CONFIG, get_settings  # noqa: E402
from app.database import create_db_engine, session_factory  # noqa: E402
from app.documents.intake import IntakeError, uploads_dir  # noqa: E402
from app.documents.repository import DocumentRepository  # noqa: E402
from app.documents.service import (  # noqa: E402
    ClientNotFoundError,
    ConflictError,
    DocumentService,
)
from app.providers import ProviderError  # noqa: E402
from app.reader.cache import ReadingCache  # noqa: E402

WORK = Path(__file__).resolve().parent / "output" / "service_check"


def main() -> None:
    manifest = json.loads((APP_CONFIG.samples_dir / "manifest.json").read_text(encoding="utf-8"))
    documents = manifest["documents"]
    by_stem = {Path(d["file"]).stem: d for d in documents}
    current = {"stem": ""}  # the cached answers follow the file being uploaded

    def extractor(reading):
        return cached_extractor(current["stem"])(reading)

    def ledger(document, client_name):
        return cached_ledger_suggester(current["stem"])(document, client_name)

    shutil.rmtree(WORK, ignore_errors=True)
    engine = create_db_engine(WORK / "check.db")
    repo = DocumentRepository(session_factory(engine)())
    service = DocumentService(
        repo,
        get_settings(),
        extractor,
        ledger,
        reading_cache=ReadingCache(WORK / "readings"),
        data_dir=WORK,
        today=lambda: TODAY,
    )

    # 1. all samples
    ids, status_ok, stored_ok, run_ok = {}, 0, 0, 0
    for entry in documents:
        path = APP_CONFIG.samples_dir / entry["file"]
        current["stem"] = path.stem
        row = service.upload(path.read_bytes(), path.name, entry["client"])
        ids[path.stem] = row.id
        status_ok += row.status == entry["expected_status"]
        stored_ok += (uploads_dir(WORK) / row.stored_filename).read_bytes() == path.read_bytes()
        run = row.pipeline_run or {}
        if entry["split"] == "dev":  # only dev documents have a cached ledger_v1 answer
            run_ok += run.get("calls") == 2 and run["prompt_versions"]["ledger"] == "ledger_v1"
    total = len(documents)
    dev = sum(d["split"] == "dev" for d in documents)
    print(
        f"UPLOAD   status equals manifest {status_ok}/{total}; "
        f"stored file identical {stored_ok}/{total}"
    )
    print(f"RUN      dev documents: 2 calls and prompt ledger_v1 recorded {run_ok}/{dev}")
    sample = service.get(ids["01-intra-classic"])
    print(f"RECORD   01: {sample.status}, {sample.document_type}, ledger {sample.ledger}")
    print(
        f"         history {[h['event'] for h in sample.history]}, run steps "
        f"{[s['step'] for s in sample.pipeline_run['steps']]}"
    )

    # 2. the same file again
    current["stem"] = "01-intra-classic"
    path = APP_CONFIG.samples_dir / by_stem["01-intra-classic"]["file"]
    again = service.upload(path.read_bytes(), "copy.pdf", by_stem["01-intra-classic"]["client"])
    codes = [i["code"] for i in again.issues or []]
    print(
        f"REUPLOAD file={'duplicate_file' in codes} invoice={'duplicate_invoice' in codes} "
        f"status={again.status} (needs_review: {again.status == 'needs_review'})"
    )

    # 3. rejected before anything is stored
    before = len(service.list())
    outcomes = []
    for label, data, client in (
        ("renamed exe", b"MZ" + b"\0" * 50, "C001"),
        ("unknown client", path.read_bytes(), "C999"),
    ):
        try:
            service.upload(data, "x.pdf", client)
            outcomes.append(f"{label}: ACCEPTED")
        except IntakeError as error:
            outcomes.append(f"{label}: {error.status_code}")
        except ClientNotFoundError:
            outcomes.append(f"{label}: unknown client")
    print(f"REJECT   {outcomes}; rows stored {len(service.list()) - before} (want 0)")

    # 4. provider fails -> failed, then retry works
    def busy_extractor(_reading):
        raise ProviderError("The AI provider is busy. Retry later.", busy=True)

    # Sample 04 and 11 were uploaded in step 1; remove those rows so they are new again.
    service.repository.delete(service.get(ids["04-inter-compact"]))
    service.repository.delete(service.get(ids["11-fuel-receipt"]))
    service.extractor = busy_extractor
    other = APP_CONFIG.samples_dir / by_stem["04-inter-compact"]["file"]
    failed = service.upload(other.read_bytes(), other.name, by_stem["04-inter-compact"]["client"])
    print(
        f"FAILED   status={failed.status} kind={failed.pipeline_run['error_kind']} "
        f"message={failed.error_message!r}"
    )
    try:
        service.retry(ids["01-intra-classic"])
        print("RETRY    BAD: a non-failed document was retried")
    except ConflictError:
        print("RETRY    non-failed document -> conflict (409): True")
    service.extractor = extractor
    current["stem"] = "04-inter-compact"
    retried = service.retry(failed.id)
    want = by_stem["04-inter-compact"]["expected_status"]
    print(
        f"RETRY    status={retried.status} (want {want}), "
        f"history {[h['event'] for h in retried.history]}"
    )

    # 5. ledger provider fails -> document kept, no suggested code
    def busy_ledger(_document, _client_name):
        raise ProviderError("busy", busy=True)

    service.ledger_suggester = busy_ledger
    current["stem"] = "11-fuel-receipt"
    fuel = APP_CONFIG.samples_dir / by_stem["11-fuel-receipt"]["file"]
    kept = service.upload(fuel.read_bytes(), fuel.name, by_stem["11-fuel-receipt"]["client"])
    print(
        f"LEDGERFAIL status={kept.status}, suggested={kept.ledger['suggested_code']}, "
        f"reason={kept.ledger['reason']!r}"
    )


if __name__ == "__main__":
    main()
