"""SQLite engine and sessions. Only the repository talks to the database."""

from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import APP_CONFIG


class Base(DeclarativeBase):
    pass


def default_db_path() -> Path:
    return APP_CONFIG.data_dir / "invoice_review.db"


def create_db_engine(path: Path | None = None) -> Engine:
    """Create the engine and the tables. Delete the .db file after a schema change (dev only)."""
    from app.documents import models  # noqa: F401  (registers the tables on Base)

    target = path or default_db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{target}")
    Base.metadata.create_all(engine)
    return engine


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
