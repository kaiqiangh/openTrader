from __future__ import annotations

import pytest

from services.market_ingestion.contracts import OrderBookLevel, OrderBookSnapshot
from services.market_ingestion.kline_validator import KlineBar
from services.market_ingestion.persistence_writers import TimescalePersistenceWriters


class _FakeTimeseriesStore:
    def __init__(self) -> None:
        self.orderbook_rows: list[dict] = []
        self.kline_rows: list[dict] = []

    async def upsert_orderbook_snapshot(self, row: dict) -> None:
        self.orderbook_rows.append(row)

    async def upsert_kline(self, row: dict) -> None:
        self.kline_rows.append(row)


@pytest.mark.asyncio
async def test_persist_orderbook_snapshot_writes_expected_record() -> None:
    store = _FakeTimeseriesStore()
    writer = TimescalePersistenceWriters(store=store)
    snapshot = OrderBookSnapshot(
        exchange="binance",
        symbol="BTC/USDT",
        sequence=301,
        timestamp_ms=1739535603000,
        bids=(OrderBookLevel(42000.0, 1.5),),
        asks=(OrderBookLevel(42001.0, 1.4),),
    )

    row = await writer.persist_orderbook_snapshot(snapshot)

    assert store.orderbook_rows[0]["table"] == "orderbook_snapshots"
    assert store.orderbook_rows[0]["sequence"] == 301
    assert store.orderbook_rows[0]["best_bid"] == 42000.0
    assert store.orderbook_rows[0]["best_ask"] == 42001.0
    assert row == store.orderbook_rows[0]


@pytest.mark.asyncio
async def test_persist_klines_deduplicates_and_sorts_open_times() -> None:
    store = _FakeTimeseriesStore()
    writer = TimescalePersistenceWriters(store=store)
    bars = [
        KlineBar(1700000120000, 11.8, 12.2, 11.0, 11.2, 90.0),
        KlineBar(1700000000000, 10.0, 11.0, 9.5, 10.5, 100.0),
        KlineBar(1700000000000, 10.2, 11.1, 9.9, 10.7, 110.0),
    ]

    written_count = await writer.persist_klines(
        exchange="binance",
        symbol="BTC/USDT",
        interval_ms=60_000,
        bars=bars,
    )

    assert written_count == 2
    assert len(store.kline_rows) == 2
    assert store.kline_rows[0]["open_time_ms"] == 1700000000000
    assert store.kline_rows[0]["open"] == 10.2
    assert store.kline_rows[1]["open_time_ms"] == 1700000120000
