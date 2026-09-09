from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.settings import get_settings
from database.models import Base


@pytest.fixture
def settings_env(monkeypatch):
    monkeypatch.setenv("APPROVAL_TOKEN_SECRET", "test-secret-do-not-use-in-prod")
    monkeypatch.setenv("APPROVAL_TOKEN_TTL_SECONDS", "3600")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture
def db_session(settings_env):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
