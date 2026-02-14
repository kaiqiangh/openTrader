from __future__ import annotations

from pathlib import Path
import sqlite3


def create_engine_from_url(database_url: str) -> sqlite3.Connection:
    """Compatibility helper used by runtime adapters in environments without SQLAlchemy."""
    if not database_url:
        raise ValueError("database_url must be non-empty")

    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("only sqlite:/// URLs are supported in this runtime helper")

    db_path = database_url[len(prefix) :]
    if not db_path:
        raise ValueError("sqlite path must be non-empty")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection
