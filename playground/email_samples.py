"""Experiment: correction-email drafts (LLM call) for documents with supplier-fixable issues.

The document and its issues come from the offline pipeline (cached reading-A answers), so the
only model call is the draft. Drafts are cached per prompt in output/<prompt>/. A new call on a
test-split document is refused unless --allow-test. Run from backend/:

    uv run --locked --no-sync python ../playground/email_samples.py --dry
    uv run --locked --no-sync python ../playground/email_samples.py --split dev
    ... --dry lists the candidates and the calls needed; --fresh ignores the cache
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline_samples import make_context  # noqa: E402

from app.config import APP_CONFIG, get_settings  # noqa: E402
from app.correction_email.eligibility import eligible_issues  # noqa: E402
from app.correction_email.schemas import EmailDraft  # noqa: E402
from app.pipeline.base import run_pipeline  # noqa: E402
from app.pipeline.steps import build_default_pipeline  # noqa: E402
from app.providers import (  # noqa: E402
    EMAIL_PROMPT,
    CallInfo,
    EmailResult,
    draft_correction_email,
    format_for_email,
)

OUTPUT = Path(__file__).resolve().parent / "output"
SECONDS_BETWEEN_CALLS = 4.5  # free tier: 15 requests per minute
INTERNAL_WORDS = re.compile(r"[a-z]+_[a-z_]+|\bAI\b|\bapp\b|input tax credit|\bITC\b", re.I)


def cached_draft(stem: str, prompt: str) -> EmailResult | None:
    path = OUTPUT / prompt / f"{stem}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return EmailResult(draft=EmailDraft(**data["draft"]), call=CallInfo(**data["call"]))


def problems_with(draft: EmailDraft, facts: str, problems: str, client_name: str) -> list[str]:
    """Automatic checks. They do not judge the wording; read the drafts yourself."""
    found = []
    text = f"{draft.subject}\n{draft.body}"
    source = (facts + problems).replace(",", "")
    for number in set(re.findall(r"\d[\d,.]{2,}\d|\d{3,}", text)):
        if number.replace(",", "") not in source:
            found.append(f"number not in the facts: {number}")
    if INTERNAL_WORDS.search(text):
        found.append(f"internal word: {INTERNAL_WORDS.search(text).group()}")  # type: ignore[union-attr]
    if len(draft.body.split()) > 200:
        found.append(f"body has {len(draft.body.split())} words")
    if "[Your name]" not in draft.body or client_name not in draft.body:
        found.append("signature block missing")
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test"])
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--allow-test", action="store_true")
    parser.add_argument("--prompt", default=EMAIL_PROMPT)
    options = parser.parse_args()

    manifest = json.loads((APP_CONFIG.samples_dir / "manifest.json").read_text(encoding="utf-8"))
    entries = [d for d in manifest["documents"] if not options.split or d["split"] == options.split]
    settings, steps = get_settings(), build_default_pipeline()
    (OUTPUT / options.prompt).mkdir(parents=True, exist_ok=True)

    candidates = []
    for entry in entries:
        context = make_context(entry, settings, None)
        run_pipeline(steps, context)
        eligible = eligible_issues(context.review.issues)  # type: ignore[union-attr]
        if eligible:
            candidates.append((entry, context, eligible))
    needed = [
        c
        for c in candidates
        if options.fresh or cached_draft(Path(c[0]["file"]).stem, options.prompt) is None
    ]
    print(
        f"prompt {options.prompt}: {len(entries)} documents, {len(candidates)} with eligible "
        f"issues, {len(needed)} need a model call"
    )
    for entry, _, eligible in candidates:
        print(f"  {entry['file']} [{entry['split']}]: {[i.code.value for i in eligible]}")
    if options.dry:
        return

    clean = 0
    for entry, context, eligible in candidates:
        stem = Path(entry["file"]).stem
        result = None if options.fresh else cached_draft(stem, options.prompt)
        if result is None:
            if entry["split"] == "test" and not options.allow_test:
                print(f"\nskipped {stem}: test split (no new model call)")
                continue
            result = draft_correction_email(
                context.document,
                context.client,
                eligible,
                settings,
                options.prompt,  # type: ignore[arg-type]
            )
            (OUTPUT / options.prompt / f"{stem}.json").write_text(
                json.dumps({"draft": result.draft.model_dump(), "call": result.call.__dict__}),
                encoding="utf-8",
            )
            time.sleep(SECONDS_BETWEEN_CALLS)
        facts, problems = format_for_email(context.document, context.client, eligible)  # type: ignore[arg-type]
        issues = problems_with(result.draft, facts, problems, context.client.name)
        clean += not issues
        print(
            f"\n=== {stem} [{result.call.input_tokens}+{result.call.output_tokens} tokens, "
            f"{result.call.seconds}s] {'CHECKS OK' if not issues else issues}"
        )
        print(f"Subject: {result.draft.subject}\n\n{result.draft.body}")
    print(f"\nDRAFTS passing the automatic checks: {clean}/{len(candidates)}")


if __name__ == "__main__":
    main()
