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
from app.schemas.extraction import Extraction  # noqa: E402
from app.schemas.issues import Severity  # noqa: E402

CACHE = Path(__file__).resolve().parent / "output" / "extract"
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
    agree = 0
    for entry in manifest["documents"]:
        path = APP_CONFIG.samples_dir / entry["file"]
        context = PipelineContext(
            data=path.read_bytes(),
            client=CLIENTS_BY_ID[entry["client"]],
            settings=settings,
            extractor=cached_extractor(path.stem),
            today=TODAY,
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


if __name__ == "__main__":
    main()
