"""LLM access through pydantic-ai. pydantic-ai and SDK types do not leave this package.

The rest of the app calls plain functions such as `extract()` and gets our own Pydantic models
back. Switching provider is the `LLM_PROVIDER` setting.
"""

import time
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import Settings
from app.reader.schemas import ReadDocument
from app.schemas.extraction import Extraction

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
EXTRACT_PROMPT = "extract_v2"


@dataclass(frozen=True)
class CallInfo:
    provider: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    seconds: float


@dataclass(frozen=True)
class ExtractionResult:
    extraction: Extraction
    call: CallInfo


def load_prompt(version: str) -> str:
    return (PROMPTS_DIR / f"{version}.md").read_text(encoding="utf-8")


def build_model(settings: Settings) -> Model:
    if settings.llm_provider == "gemini":
        assert settings.gemini_api_key is not None
        return GoogleModel(
            settings.active_model,
            provider=GoogleProvider(api_key=settings.gemini_api_key.get_secret_value()),
        )
    # NVIDIA's hosted models speak the OpenAI chat API. Not verified yet (no key configured).
    assert settings.nvidia_api_key is not None
    return OpenAIChatModel(
        settings.active_model,
        provider=OpenAIProvider(
            base_url=settings.nvidia_base_url,
            api_key=settings.nvidia_api_key.get_secret_value(),
        ),
    )


def format_words(document: ReadDocument) -> str:
    """One text line per document line: `p1 L5 | w21:Invoice w22:No: w23:SSM/26-27/0412`."""
    lines: dict[tuple[int, int], list[str]] = {}
    for word in document.words:
        lines.setdefault((word.page, word.line), []).append(f"{word.id}:{word.text}")
    return "\n".join(
        f"p{page} L{line} | {' '.join(tokens)}" for (page, line), tokens in sorted(lines.items())
    )


def extract(
    document: ReadDocument, settings: Settings, prompt_version: str = EXTRACT_PROMPT
) -> ExtractionResult:
    """Reading A: classify the document and extract fields with evidence word IDs.

    `prompt_version` defaults to the prompt the app uses; experiments pass another file name
    from `prompts/`. The version is recorded in the returned `CallInfo`.
    """
    agent = Agent(
        build_model(settings),
        output_type=Extraction,
        instructions=load_prompt(prompt_version),
        retries=1,
    )
    started = time.perf_counter()
    result = agent.run_sync(f"<document>\n{format_words(document)}\n</document>")
    usage = result.usage
    return ExtractionResult(
        extraction=result.output,
        call=CallInfo(
            provider=settings.llm_provider,
            model=settings.active_model,
            prompt_version=prompt_version,
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
            seconds=round(time.perf_counter() - started, 2),
        ),
    )
