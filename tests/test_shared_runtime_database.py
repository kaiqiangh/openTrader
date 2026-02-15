from __future__ import annotations

import pytest

from services.shared.runtime.database import (
    RuntimeDatabaseConfigError,
    create_runtime_engine_from_env,
    load_runtime_database_settings,
)
from services.shared.runtime.sqlalchemy_utils import create_engine_from_url


def test_load_runtime_database_settings_prefers_database_url() -> None:
    settings = load_runtime_database_settings(
        env={
            "DATABASE_URL": "postgresql+psycopg://user:pass@postgres:5432/open_trader",
            "ALLOW_SQLITE_RUNTIME": "false",
        }
    )
    assert settings.database_url == "postgresql+psycopg://user:pass@postgres:5432/open_trader"
    assert settings.allow_sqlite_runtime is False


def test_load_runtime_database_settings_builds_postgres_url_from_components() -> None:
    settings = load_runtime_database_settings(
        env={
            "POSTGRES_HOST": "db",
            "POSTGRES_PORT": "5439",
            "POSTGRES_DB": "ot",
            "POSTGRES_USER": "ot_user",
            "POSTGRES_PASSWORD": "ot pass",
            "ALLOW_SQLITE_RUNTIME": "false",
        }
    )
    assert settings.database_url == "postgresql+psycopg://ot_user:ot+pass@db:5439/ot"


def test_sqlite_runtime_is_rejected_without_override() -> None:
    with pytest.raises(RuntimeDatabaseConfigError):
        load_runtime_database_settings(
            env={
                "DATABASE_URL": "sqlite+pysqlite:///:memory:",
                "ALLOW_SQLITE_RUNTIME": "false",
            }
        )


def test_sqlite_runtime_can_be_enabled_for_local_tests() -> None:
    settings = load_runtime_database_settings(
        env={
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "ALLOW_SQLITE_RUNTIME": "true",
        }
    )
    assert settings.allow_sqlite_runtime is True
    engine = create_runtime_engine_from_env(
        env={
            "DATABASE_URL": settings.database_url,
            "ALLOW_SQLITE_RUNTIME": "true",
        }
    )
    with engine.connect() as connection:
        value = connection.exec_driver_sql("SELECT 1").scalar_one()
    assert value == 1


def test_create_engine_from_url_accepts_postgres_url_shape() -> None:
    # This validates URL parsing/engine construction only; it does not connect to Postgres.
    engine = create_engine_from_url("postgresql+psycopg://user:pass@localhost:5432/open_trader")
    assert engine.url.drivername == "postgresql+psycopg"
