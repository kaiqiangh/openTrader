from __future__ import annotations

import pytest

from services.market_ingestion.contracts import OrderBookDelta, OrderBookLevel, OrderBookSnapshot
from services.market_ingestion.order_book_sync import (
    OrderBookSequenceGapError,
    OrderBookSyncEngine,
)


def _snapshot(sequence: int) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        exchange="binance",
        symbol="BTC/USDT",
        sequence=sequence,
        timestamp_ms=1739535600000,
        bids=(OrderBookLevel(42000.0, 1.0), OrderBookLevel(41999.0, 2.0)),
        asks=(OrderBookLevel(42001.0, 1.0), OrderBookLevel(42002.0, 2.0)),
    )


def _delta(sequence_start: int, sequence_end: int) -> OrderBookDelta:
    return OrderBookDelta(
        exchange="binance",
        symbol="BTC/USDT",
        sequence_start=sequence_start,
        sequence_end=sequence_end,
        timestamp_ms=1739535600500,
        bids=(OrderBookLevel(42000.0, 1.5), OrderBookLevel(41999.0, 0.0)),
        asks=(OrderBookLevel(42001.0, 0.0), OrderBookLevel(42003.0, 1.0)),
    )


def test_apply_delta_updates_and_deletes_levels() -> None:
    engine = OrderBookSyncEngine(exchange="binance", symbol="BTC/USDT")
    engine.load_snapshot(_snapshot(sequence=100))

    applied = engine.apply_delta(_delta(sequence_start=101, sequence_end=101))
    materialized = engine.materialize_snapshot(depth=3)

    assert applied is True
    assert materialized["sequence"] == 101
    assert materialized["bids"][0]["price"] == 42000.0
    assert len(materialized["bids"]) == 1
    assert materialized["asks"][0]["price"] == 42002.0


def test_apply_delta_raises_gap_error_when_sequence_skips() -> None:
    engine = OrderBookSyncEngine(exchange="binance", symbol="BTC/USDT")
    engine.load_snapshot(_snapshot(sequence=100))

    with pytest.raises(OrderBookSequenceGapError):
        engine.apply_delta(_delta(sequence_start=105, sequence_end=105))


def test_apply_delta_ignores_stale_delta() -> None:
    engine = OrderBookSyncEngine(exchange="binance", symbol="BTC/USDT")
    engine.load_snapshot(_snapshot(sequence=100))

    applied = engine.apply_delta(_delta(sequence_start=90, sequence_end=100))
    materialized = engine.materialize_snapshot(depth=3)

    assert applied is False
    assert materialized["sequence"] == 100
