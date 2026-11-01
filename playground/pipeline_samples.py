"""Experiment: run the whole pipeline on every sample, offline. No API calls.

The extraction step gets the cached reading-A output (`output/extract/`) instead of calling
Gemini, so this checks the pipeline wiring (reading -> extraction -> grounding -> validation) and
compares status and blocking codes with manifest.json. Run from backend/:

    uv run --locked --no-sync python ../playground/pipeline_samples.py
"""

import json
import sys
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.clients import CLIENTS_BY_ID  # noqa: E402
from app.config import APP_CONFIG, get_settings  # noqa: E402
from app.pipeline.base import PipelineContext, run_pipeline  # noqa: E402
from app.pipeline.steps import build_default_pipeline  # noqa: E402
from app.providers import CallInfo, ExtractionResult  # noqa: E402
from app.reader import read_document  # noqa: E402
from app.reader.cache import ReadingCache  # noqa: E402
from app.schemas.extraction import Extraction  # noqa: E402
from app.schemas.issues import Severity  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "output"
CACHE = OUTPUT / "extract"
TODAY = date(2026, 10, 31)  # the samples are dated Aug - Oct 2026


def cached_extractor(stem: str):
    cached = json.loads((CACHE / f"{stem}.json").read_text(encoding="utf-8"))

    def extractor(_reading) -> ExtractionResult:
        return ExtractionResult(
            extraction=Extraction.model_validate(cached["extraction"]),
            call=CallInfo(**cached["call"]),
        )

    return extractor


def main() -> None:
    manifest = json.loads((APP_CONFIG.samples_dir / "manifest.json").read_text(encoding="utf-8"))
    settings = get_settings()
    steps = build_default_pipeline()
    reading_cache = ReadingCache(OUTPUT / "readings")
    for old in reading_cache.directory.glob("*.json"):
        old.unlink()  # start cold so the first pass really reads
    agree = 0
    for entry in manifest["documents"]:
        path = APP_CONFIG.samples_dir / entry["file"]
        context = PipelineContext(
            data=path.read_bytes(),
            client=CLIENTS_BY_ID[entry["client"]],
            settings=settings,
            extractor=cached_extractor(path.stem),
            today=TODAY,
            reading_cache=reading_cache,
        )
        context, error = run_pipeline(steps, context)
        errors = (
            {i.code.value for i in context.review.issues if i.severity == Severity.ERROR}
            if context.review
            else set()
        )
        ok = (
            error is None
            and context.status == entry["expected_status"]
            and errors == set(entry["expected_errors"])
        )
        agree += ok
        timings = " ".join(f"{t.step}={t.ms}ms" for t in context.trace)
        print(f"{'OK ' if ok else 'BAD'} {entry['file']}: {context.status} | {timings}")
        if error:
            print(f"      failed: {error}")
        elif not ok:
            print(f"      errors {sorted(errors)} want {sorted(entry['expected_errors'])}")
    print(f"\nAGREE {agree}/{len(manifest['documents'])} documents (status and errors)")
    check_cache_and_duplicates(manifest, settings, steps, reading_cache)


def make_context(entry, settings, reading_cache, known=None) -> PipelineContext:
    path = APP_CONFIG.samples_dir / entry["file"]
    return PipelineContext(
        data=path.read_bytes(),
        client=CLIENTS_BY_ID[entry["client"]],
        settings=settings,
        extractor=cached_extractor(path.stem),
        today=TODAY,
        reading_cache=reading_cache,
        known_files=known or {},
    )


def check_cache_and_duplicates(manifest, settings, steps, reading_cache) -> None:
    """Second pass: reading comes from the cache. Re-upload: every file is flagged once."""
    documents = manifest["documents"]
    total = len(documents)
    hits = same = flagged = status_kept = warm_ms = 0
    known: dict[str, str] = {}
    for entry in documents:
        context = make_context(entry, settings, reading_cache)
        known[context.sha256] = entry["file"]
        run_pipeline(steps, context)
        hits += context.cache_hit
        warm_ms += next(t.ms for t in context.trace if t.step == "reading")
        same += context.reading == read_document(context.data).document
    for entry in documents:
        context = make_context(entry, settings, reading_cache, known)
        run_pipeline(steps, context)
        codes = [i.code.value for i in context.review.issues]
        flagged += codes.count("duplicate_file") == 1
        status_kept += context.status == entry["expected_status"]
    print(f"CACHE   hits {hits}/{total}; cached words identical to a fresh read {same}/{total}")
    print(f"        reading time with the cache: {warm_ms} ms in total")
    print(
        f"DUPFILE flagged once on re-upload {flagged}/{total}; "
        f"status unchanged {status_kept}/{total}"
    )


if __name__ == "__main__":
    main()
