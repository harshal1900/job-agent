"""SQLite/Supabase connection switch.

SQLite is the default dev/offline backend. Swapping to Supabase later should
only require setting DB_BACKEND=supabase and SUPABASE_DB_URL in .env — no
model or query code should need to change, since models.py targets
Postgres-compatible types already.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import get_settings
from database.models import Base

_engine = None
_SessionLocal: sessionmaker | None = None


def _build_engine():
    settings = get_settings()

    if settings.DB_BACKEND == "supabase":
        if not settings.SUPABASE_DB_URL:
            raise RuntimeError(
                "DB_BACKEND=supabase but SUPABASE_DB_URL is not set in .env"
            )
        return create_engine(settings.SUPABASE_DB_URL, pool_pre_ping=True)

    # sqlite default
    db_path = Path(settings.SQLITE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )


def get_engine():
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(), autoflush=False, autocommit=False
        )
    return _SessionLocal


def init_db() -> None:
    """Create all tables. Safe to call repeatedly (no-op if they exist)."""
    Base.metadata.create_all(bind=get_engine())


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
