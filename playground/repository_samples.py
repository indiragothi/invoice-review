"""Experiment: store the 12 pipeline results in SQLite and read them back. Offline, no API calls.

Checks the repository against the manifest: list and filters, the duplicate keys loaded from
the database, `known_files`, and that a re-upload of every sample is flagged by the real
duplicate rules (file and content) while a rejected record is ignored. Uses a throw-away
database in playground/output/. Run from backend/:

    uv run --locked --no-sync python ../playground/repository_samples.py
"""

import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import json  # noqa: E402

from pipeline_samples import make_context  # noqa: E402

from app.config import APP_CONFIG, get_settings  # noqa: E402
from app.database import create_db_engine, session_factory  # noqa: E402
from app.documents.models import DocumentStatus  # noqa: E402
from app.documents.repository import DocumentRepository  # noqa: E402
from app.pipeline.base import run_pipeline  # noqa: E402
from app.pipeline.steps import build_default_pipeline  # noqa: E402
from app.validation.duplicates import invoice_key, key_to_json, receipt_key  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "output"


def main() -> None:
    manifest = json.loads((APP_CONFIG.samples_dir / "manifest.json").read_text(encoding="utf-8"))
    documents = manifest["documents"]
    settings, steps = get_settings(), build_default_pipeline()

    db_path = OUTPUT / "repository_check.db"
    db_path.unlink(missing_ok=True)
    engine = create_db_engine(db_path)
    repo = DocumentRepository(session_factory(engine)())

    ids: dict[str, str] = {}
    for entry in documents:
        context = make_context(entry, settings, None)
        run_pipeline(steps, context)
        assert context.document is not None and context.review and context.ledger
        key = (invoice_key if context.document.document_type == "invoice" else receipt_key)(
            context.document  # type: ignore[arg-type]
        )
        row = repo.create(
            client_id=entry["client"],
            original_filename=Path(entry["file"]).name,
            stored_filename=f"{Path(entry['file']).stem}.stored",
            content_type=context.reading.content_type,  # type: ignore[union-attr]
            sha256=context.sha256,
            page_count=len(context.reading.pages),  # type: ignore[union-attr]
            status=context.status,
            document_type=context.document.document_type,
            duplicate_key=key_to_json(key) if key else None,
            issues=[i.model_dump(mode="json") for i in context.review.issues],
            ledger=context.ledger.model_dump(),
        )
        ids[entry["file"]] = row.id

    total = len(documents)
    want = Counter(d["expected_status"] for d in documents)
    got = Counter(r.status for r in repo.list())
    print(f"LIST      {len(repo.list())}/{total} stored; statuses {dict(got)} want {dict(want)}")
    for status in ("ready", "needs_review"):
        n = len(repo.list(status=status))
        print(f"FILTER    status={status}: {n} (want {want[status]})")
    for client in sorted({d["client"] for d in documents}):
        n = len(repo.list(client_id=client))
        print(
            f"FILTER    client={client}: {n} (want {sum(d['client'] == client for d in documents)})"
        )

    # Re-upload every sample: the database must supply what the pipeline needs to flag it.
    file_hits = content_hits = 0
    for entry in documents:
        own = ids[entry["file"]]
        context = make_context(entry, settings, None, repo.known_files(exclude_id=own))
        context.existing_keys = lambda kind, c=entry["client"], o=own: repo.existing_keys(
            c, kind, o
        )
        run_pipeline(steps, context)
        codes = [i.code.value for i in context.review.issues]  # type: ignore[union-attr]
        file_hits += codes.count("duplicate_file") == 0  # excluded itself: no file match
        content_hits += not ({"duplicate_invoice", "duplicate_receipt"} & set(codes))
    print(
        f"SELF      document excluded from its own checks: {file_hits}/{total} file, "
        f"{content_hits}/{total} content"
    )

    # A copy of one sample uploaded again is flagged on both counts.
    sample = documents[0]
    context = make_context(sample, settings, None, repo.known_files())
    context.existing_keys = lambda kind: repo.existing_keys(sample["client"], kind)
    run_pipeline(steps, context)
    codes = [i.code.value for i in context.review.issues]  # type: ignore[union-attr]
    print(
        f"REUPLOAD  {sample['file']}: duplicate_file={'duplicate_file' in codes} "
        f"duplicate_invoice={'duplicate_invoice' in codes} status={context.status}"
    )

    # Rejected records stop counting as duplicates.
    repo.update(repo.get(ids[sample["file"]]), status=DocumentStatus.REJECTED)  # type: ignore[arg-type]
    after = repo.existing_keys(sample["client"], "invoice")
    print(f"REJECTED  ignored for duplicate keys: {ids[sample['file']] not in after}")

    # Update and delete.
    row = repo.get(ids[sample["file"]])
    repo.delete(row)  # type: ignore[arg-type]
    print(f"DELETE    gone: {repo.get(ids[sample['file']]) is None}; left {len(repo.list())}")


if __name__ == "__main__":
    main()
