"""LLM access through pydantic-ai. pydantic-ai and SDK types do not leave this package.

The rest of the app calls plain functions such as `extract()` and gets our own Pydantic models
back. Switching provider is the `LLM_PROVIDER` setting.
"""

import time
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.models import Model
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider

from app.accounting.catalog import catalog_for_prompt
from app.config import APP_CONFIG, Settings
from app.providers.retry import ProviderError, retry_with_backoff
from app.reader.schemas import ReadDocument
from app.schemas.documents import Invoice, Receipt
from app.schemas.extraction import Extraction
from app.schemas.ledger import LedgerChoice

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
EXTRACT_PROMPT = "extract_v2"
LEDGER_PROMPT = "ledger_v1"

_BUSY_STATUS = {429, 500, 502, 503, 504}


def _is_busy(error: Exception) -> bool:
    return isinstance(error, ModelHTTPError) and error.status_code in _BUSY_STATUS


def _run_agent[T](agent: Agent[None, T], prompt: str):
    """Run one agent call with retry on 429 / 5xx; SDK errors become `ProviderError`."""
    try:
        return retry_with_backoff(
            lambda: agent.run_sync(prompt), APP_CONFIG.provider_retry_delays, _is_busy
        )
    except (ModelAPIError, UnexpectedModelBehavior) as error:
        if _is_busy(error):
            raise ProviderError("The AI provider is busy. Retry later.", busy=True) from error
        raise ProviderError(
            "The AI provider could not process this document.", busy=False
        ) from error


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
    result = _run_agent(agent, f"<document>\n{format_words(document)}\n</document>")
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


@dataclass(frozen=True)
class LedgerResult:
    choice: LedgerChoice
    call: CallInfo


def format_for_ledger(document: Invoice | Receipt, client_name: str) -> str:
    """The normalised fields the ledger decision needs. No raw file text, no boxes."""
    if isinstance(document, Invoice):
        lines = ["Kind: invoice", f"Vendor: {document.vendor_name}"]
    else:
        lines = ["Kind: receipt", f"Merchant: {document.merchant_name}"]
    lines.insert(0, f"Buyer: {client_name}")
    for number, item in enumerate(document.line_items, start=1):
        lines.append(
            f"Item {number}: {item.description} | HSN/SAC {item.hsn_sac} | {item.taxable_amount}"
        )
    lines.append(f"Total: {document.total}")
    return "\n".join(lines)


def suggest_ledger(
    document: Invoice | Receipt,
    client_name: str,
    settings: Settings,
    prompt_version: str = LEDGER_PROMPT,
) -> LedgerResult:
    """One LLM call: pick a ledger code from the catalog. The caller must still check the code
    with `checked_ledger_code`; nothing here trusts the model."""
    agent = Agent(
        build_model(settings),
        output_type=LedgerChoice,
        instructions=load_prompt(prompt_version),
        retries=1,
    )
    prompt = (
        f"<catalog>\n{catalog_for_prompt()}\n</catalog>\n"
        f"<document>\n{format_for_ledger(document, client_name)}\n</document>"
    )
    started = time.perf_counter()
    result = _run_agent(agent, prompt)
    usage = result.usage
    return LedgerResult(
        choice=result.output,
        call=CallInfo(
            provider=settings.llm_provider,
            model=settings.active_model,
            prompt_version=prompt_version,
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
            seconds=round(time.perf_counter() - started, 2),
        ),
    )
