from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import APP_CONFIG, get_settings
from app.database import create_db_engine, session_factory
from app.documents import routes as document_routes
from app.documents.service import EmailDrafter
from app.pipeline.base import Extractor, LedgerSuggester
from app.providers import draft_correction_email, extract, suggest_ledger
from app.reader.cache import ReadingCache
from app.reference_routes import router as reference_router


def create_app(
    data_dir: Path | None = None,
    extractor: Extractor | None = None,
    ledger_suggester: LedgerSuggester | None = None,
    email_drafter: EmailDrafter | None = None,
) -> FastAPI:
    """Build the app. The arguments exist so a check can use a temporary folder and cached model
    answers; the running server passes none of them and uses `backend/data/` and the real models."""
    settings = get_settings()
    base = data_dir or APP_CONFIG.data_dir

    app = FastAPI(title="Invoice Review", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.allowed_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.settings = settings
    app.state.data_dir = base
    app.state.session_factory = session_factory(create_db_engine(base / "invoice_review.db"))
    app.state.reading_cache = ReadingCache(base / "cache" / "readings")
    app.state.extractor = extractor or (lambda reading: extract(reading, settings))
    app.state.ledger_suggester = ledger_suggester or (
        lambda document, client_name: suggest_ledger(document, client_name, settings)
    )

    app.state.email_drafter = email_drafter or (
        lambda document, client, issues: draft_correction_email(document, client, issues, settings)
    )

    app.include_router(reference_router)
    app.include_router(document_routes.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "llm_provider": settings.llm_provider,
            "model": settings.active_model,
        }

    return app
