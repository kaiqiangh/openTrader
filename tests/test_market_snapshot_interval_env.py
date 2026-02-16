from __future__ import annotations

from services.workers.main import _market_worker_cycle_interval_seconds


def test_orderbook_snapshot_interval_overrides_rest_poll(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_DATA_FETCH_MODE", "rest")
    monkeypatch.setenv("MARKET_DATA_REST_POLL_SECONDS", "300")
    monkeypatch.setenv("ORDERBOOK_SNAPSHOT_INTERVAL_SECONDS", "180")

    assert _market_worker_cycle_interval_seconds() == 180.0
