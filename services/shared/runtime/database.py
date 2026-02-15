from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.parse import quote_plus
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from services.shared.runtime.env_loader import load_dotenv_file


@dataclass(frozen=True, slots=True)
class RuntimeDatabaseSettings:
    database_url: str
    pool_pre_ping: bool = True
    pool_size: int = 5
    max_overflow: int = 10
    pool_recycle_seconds: int = 1800
    allow_sqlite_runtime: bool = False


class RuntimeDatabaseConfigError(ValueError):
    """Raised when runtime database settings are invalid for production-like usage."""


def load_runtime_database_settings(
    env: Mapping[str, str] | None = None,
) -> RuntimeDatabaseSettings:
    load_dotenv_file()
    source = dict(os.environ if env is None else env)
    database_url = _build_database_url(source)
    allow_sqlite_runtime = _to_bool(source.get("ALLOW_SQLITE_RUNTIME", "false"))
    if database_url.startswith("sqlite") and not allow_sqlite_runtime:
        raise RuntimeDatabaseConfigError(
            "sqlite runtime database is disabled; configure DATABASE_URL or POSTGRES_* for PostgreSQL/TimescaleDB"
        )
    return RuntimeDatabaseSettings(
        database_url=database_url,
        pool_pre_ping=_to_bool(source.get("DB_POOL_PRE_PING", "true")),
        pool_size=max(1, int(source.get("DB_POOL_SIZE", "5"))),
        max_overflow=max(0, int(source.get("DB_MAX_OVERFLOW", "10"))),
        pool_recycle_seconds=max(60, int(source.get("DB_POOL_RECYCLE_SECONDS", "1800"))),
        allow_sqlite_runtime=allow_sqlite_runtime,
    )


def create_runtime_engine(
    settings: RuntimeDatabaseSettings,
) -> Engine:
    kwargs: dict[str, object] = {
        "pool_pre_ping": settings.pool_pre_ping,
        "future": True,
    }
    if not settings.database_url.startswith("sqlite"):
        kwargs.update(
            {
                "pool_size": settings.pool_size,
                "max_overflow": settings.max_overflow,
                "pool_recycle": settings.pool_recycle_seconds,
            }
        )
    return create_engine(settings.database_url, **kwargs)


def create_runtime_engine_from_env(
    env: Mapping[str, str] | None = None,
) -> Engine:
    settings = load_runtime_database_settings(env=env)
    return create_runtime_engine(settings)


def _build_database_url(source: Mapping[str, str]) -> str:
    direct_url = source.get("DATABASE_URL", "").strip()
    if direct_url:
        return direct_url

    host = source.get("POSTGRES_HOST", "postgres").strip()
    port = source.get("POSTGRES_PORT", "5432").strip()
    db_name = source.get("POSTGRES_DB", "open_trader").strip()
    user = source.get("POSTGRES_USER", "open_trader").strip()
    password = source.get("POSTGRES_PASSWORD", "change_me").strip()
    if not host:
        raise RuntimeDatabaseConfigError("POSTGRES_HOST must be set when DATABASE_URL is not provided")
    if not db_name:
        raise RuntimeDatabaseConfigError("POSTGRES_DB must be set when DATABASE_URL is not provided")
    if not user:
        raise RuntimeDatabaseConfigError("POSTGRES_USER must be set when DATABASE_URL is not provided")
    encoded_password = quote_plus(password)
    return f"postgresql+psycopg://{user}:{encoded_password}@{host}:{port}/{db_name}"


def _to_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise RuntimeDatabaseConfigError(f"invalid boolean value: {value}")
