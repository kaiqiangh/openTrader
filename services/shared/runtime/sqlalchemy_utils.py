from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from services.shared.runtime.database import create_runtime_engine, load_runtime_database_settings


def create_engine_from_url(database_url: str) -> Engine:
    """Create a SQLAlchemy engine for runtime/test database URLs."""
    if not database_url or not database_url.strip():
        raise ValueError("database_url must be non-empty")
    return create_engine(database_url.strip(), future=True, pool_pre_ping=True)


def create_engine_from_env(env: Mapping[str, str] | None = None) -> Engine:
    settings = load_runtime_database_settings(env=env)
    return create_runtime_engine(settings)
