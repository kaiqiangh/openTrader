from __future__ import annotations

import pytest

from services.market_ingestion.canonical_pipeline import CanonicalNormalizationPipeline
from services.market_ingestion.contracts import OrderBookDelta, OrderBookLevel, OrderBookSnapshot
from services.market_ingestion.gap_detection import GapDetectionModule
from services.market_ingestion.kline_validator import KlineBar, KlineReconstructionValidator
from services.market_ingestion.order_book_sync import OrderBookSequenceGapError, OrderBookSyncEngine
from services.shared.runtime.broker import InMemoryTopicBroker


def _level(price: float, amount: float) -> OrderBookLevel:
    return OrderBookLevel(price=price, amount=amount)


def test_p9_integrity_gap_detection_resync_and_stale_paths() -> None:
    detector = GapDetectionModule()

    gap = detector.evaluate(current_sequence=200, incoming_start=205, incoming_end=208)
    assert gap.has_gap is True
    assert gap.action == "resync"
    assert gap.expected_sequence == 201
    assert gap.gap_size == 4

    request = detector.build_resync_request(
        exchange="binance",
        symbol="BTC/USDT",
        result=gap,
        reason="phase9_integrity_audit",
    )
    assert request["expected_sequence"] == 201
    assert request["received_sequence_start"] == 205
    assert request["reason"] == "phase9_integrity_audit"

    stale = detector.evaluate(current_sequence=200, incoming_start=190, incoming_end=200)
    assert stale.has_gap is False
    assert stale.action == "ignore_stale"


def test_p9_integrity_orderbook_gap_fault_then_snapshot_recovery() -> None:
    sync = OrderBookSyncEngine(exchange="binance", symbol="BTC/USDT")
    sync.load_snapshot(
        OrderBookSnapshot(
            exchange="binance",
            symbol="BTC/USDT",
            sequence=100,
            timestamp_ms=1_739_535_600_000,
            bids=(_level(42000.0, 5.0),),
            asks=(_level(42001.0, 3.0),),
        )
    )

    accepted = sync.apply_delta(
        OrderBookDelta(
            exchange="binance",
            symbol="BTC/USDT",
            sequence_start=101,
            sequence_end=101,
            timestamp_ms=1_739_535_600_100,
            bids=(_level(42000.0, 6.0),),
            asks=(_level(42001.0, 2.5),),
        )
    )
    assert accepted is True

    with pytest.raises(OrderBookSequenceGapError):
        sync.apply_delta(
            OrderBookDelta(
                exchange="binance",
                symbol="BTC/USDT",
                sequence_start=104,
                sequence_end=104,
                timestamp_ms=1_739_535_600_400,
                bids=(_level(42000.0, 7.0),),
                asks=(_level(42001.0, 2.0),),
            )
        )

    # Resync by reloading fresh snapshot near latest known sequence.
    sync.load_snapshot(
        OrderBookSnapshot(
            exchange="binance",
            symbol="BTC/USDT",
            sequence=103,
            timestamp_ms=1_739_535_600_350,
            bids=(_level(42000.0, 6.5), _level(41999.0, 1.0)),
            asks=(_level(42001.0, 2.2),),
        )
    )
    recovered = sync.apply_delta(
        OrderBookDelta(
            exchange="binance",
            symbol="BTC/USDT",
            sequence_start=104,
            sequence_end=104,
            timestamp_ms=1_739_535_600_450,
            bids=(_level(42000.0, 7.0),),
            asks=(_level(42001.0, 2.0),),
        )
    )
    assert recovered is True

    snapshot = sync.materialize_snapshot(depth=2)
    assert snapshot["sequence"] == 104
    assert snapshot["bids"][0]["price"] == 42000.0
    assert snapshot["bids"][0]["amount"] == 7.0


def test_p9_integrity_kline_reconstruction_fault_detection() -> None:
    validator = KlineReconstructionValidator(interval_ms=60_000)
    bars = [
        KlineBar(1_700_000_000_000, 10.0, 11.0, 9.5, 10.4, 100.0),
        KlineBar(1_700_000_120_000, 10.4, 11.2, 10.0, 10.9, 120.0),  # missing 1_700_000_060_000
        KlineBar(1_700_000_150_000, 10.9, 11.0, 10.5, 10.7, 90.0),  # interval mismatch (30s)
    ]

    result = validator.validate(bars)
    assert result.is_valid is False
    assert 1_700_000_060_000 in result.missing_open_times
    assert any("interval mismatch" in error for error in result.errors)


@pytest.mark.asyncio
async def test_p9_integrity_canonical_kline_validation_envelope_carries_faults() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    pipeline = CanonicalNormalizationPipeline(publisher=broker)

    bars = [
        KlineBar(1_700_000_000_000, 10.0, 11.0, 9.5, 10.4, 100.0),
        KlineBar(1_700_000_120_000, 10.4, 11.2, 10.0, 10.9, 120.0),
    ]
    envelope = await pipeline.publish_kline_validation(
        exchange="binance",
        symbol="BTC/USDT",
        interval_ms=60_000,
        bars=bars,
        mode="MOCK",
    )

    queued = await broker.consume(queue_name="market.canonical", timeout_seconds=0.0)
    assert queued is not None
    assert queued["event_type"] == "market.canonical.kline_validation"
    assert queued["idempotency_key"] == envelope["idempotency_key"]

    payload = queued["payload"]
    assert isinstance(payload, dict)
    validation = payload["validation"]
    assert validation["is_valid"] is False
    assert validation["missing_open_times"] == [1_700_000_060_000]
