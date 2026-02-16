from __future__ import annotations

from datetime import UTC, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, text


def _load_workflow_module():
    module_name = "mock_realtime_workflow_test_news_module"
    spec = spec_from_file_location(module_name, Path("scripts/mock_realtime_workflow_test.py"))
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_news_context_falls_back_to_latest_summary_when_lookback_misses() -> None:
    module = _load_workflow_module()
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    generated_at = (datetime.now(UTC) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE news_summaries (
                    summary_id TEXT PRIMARY KEY,
                    summary_text TEXT NOT NULL,
                    generated_at TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO news_summaries (summary_id, summary_text, generated_at)
                VALUES (:summary_id, :summary_text, :generated_at)
                """
            ),
            {"summary_id": "summary-1", "summary_text": "stale-but-valid", "generated_at": generated_at},
        )

    context = module._fetch_latest_news_context(engine=engine, lookback_minutes=5)  # type: ignore[attr-defined]
    assert context.summary_id == "summary-1"
    assert context.summary_text == "stale-but-valid"


def test_news_context_raises_when_no_summary_rows_exist() -> None:
    module = _load_workflow_module()
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE news_summaries (
                    summary_id TEXT PRIMARY KEY,
                    summary_text TEXT NOT NULL,
                    generated_at TEXT NOT NULL
                )
                """
            )
        )

    with pytest.raises(RuntimeError, match="No news_summaries row found"):
        module._fetch_latest_news_context(engine=engine, lookback_minutes=5)  # type: ignore[attr-defined]
