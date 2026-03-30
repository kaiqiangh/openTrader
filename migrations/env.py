from __future__ import annotations

from logging.config import fileConfig
import os
from urllib.parse import quote_plus

from alembic import context
from sqlalchemy import engine_from_config, pool

from services.shared.runtime.env_loader import load_dotenv_file

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set metadata when SQLAlchemy models are added.
target_metadata = None


def _db_url() -> str:
    load_dotenv_file()
    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return explicit

    host = os.getenv("POSTGRES_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = os.getenv("POSTGRES_PORT", "5432").strip() or "5432"
    database = os.getenv("POSTGRES_DB", "open_trader").strip() or "open_trader"
    user = os.getenv("POSTGRES_USER", "open_trader").strip() or "open_trader"
    password = os.getenv("POSTGRES_PASSWORD", "change_me")
    return (
        f"postgresql+psycopg://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{database}"
    )


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""
    context.configure(
        url=_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode."""
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _db_url()

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
