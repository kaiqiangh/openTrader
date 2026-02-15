from services.integrity_service import (
    GapDetectionModule,
    KlineBar,
    KlineReconstructionValidator,
    OrderBookSyncEngine,
)
from services.market_ingestion.contracts import OrderBookDelta, OrderBookLevel, OrderBookSnapshot


def test_integrity_service_reexports_gap_detection_and_kline_validator() -> None:
    detector = GapDetectionModule()
    result = detector.evaluate(current_sequence=10, incoming_start=12, incoming_end=13)
    assert result.has_gap is True
    assert result.action == "resync"

    validator = KlineReconstructionValidator(interval_ms=60_000)
    validation = validator.validate(
        bars=(
            KlineBar(open_time_ms=0, open=1.0, high=1.2, low=0.9, close=1.1, volume=10.0),
            KlineBar(open_time_ms=60_000, open=1.1, high=1.3, low=1.0, close=1.2, volume=8.0),
        )
    )
    assert validation.is_valid is True


def test_integrity_service_reexports_order_book_sync_engine() -> None:
    engine = OrderBookSyncEngine(exchange="binance", symbol="BTC/USDT")
    engine.load_snapshot(
        OrderBookSnapshot(
            exchange="binance",
            symbol="BTC/USDT",
            sequence=100,
            timestamp_ms=1,
            bids=(OrderBookLevel(price=100.0, amount=2.0),),
            asks=(OrderBookLevel(price=101.0, amount=1.5),),
        )
    )
    delta = OrderBookDelta(
        exchange="binance",
        symbol="BTC/USDT",
        sequence_start=101,
        sequence_end=101,
        timestamp_ms=1,
        bids=(OrderBookLevel(price=100.0, amount=2.2),),
        asks=(OrderBookLevel(price=101.0, amount=1.4),),
    )
    applied = engine.apply_delta(delta)
    assert applied is True
    materialized: dict[str, object] = engine.materialize_snapshot()
    assert materialized["sequence"] == 101
