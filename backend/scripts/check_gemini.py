"""Check that the configured LLM answers with structured output. Uses exactly 1 API call.

Run from backend/:

    uv run --locked --no-sync python -m scripts.check_gemini
"""

import time

from pydantic import BaseModel
from pydantic_ai import Agent

from app.config import get_settings
from app.providers import build_model


class Answer(BaseModel):
    document_type: str
    gstin: str


def main() -> None:
    settings = get_settings()
    print(f"Provider: {settings.llm_provider}   Model: {settings.active_model}")
    agent = Agent(build_model(settings), output_type=Answer)
    started = time.perf_counter()
    result = agent.run_sync(
        "Is this an invoice or a receipt, and what is the seller's GSTIN?\n"
        "TAX INVOICE  Sai Stationery Mart  GSTIN: 23QSSPM6142B1ZF  Bill To: Shree Ganesh Traders"
    )
    usage = result.usage
    print(f"Output: {result.output.model_dump()}")
    print(
        f"Tokens in/out: {usage.input_tokens}/{usage.output_tokens}   "
        f"Time: {time.perf_counter() - started:.1f}s"
    )
    print("OK: structured output works.")


if __name__ == "__main__":
    main()
