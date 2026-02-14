from __future__ import annotations

import pytest

from services.market_ingestion.canonical_pipeline import CanonicalNormalizationPipeline
from services.market_ingestion.contracts import OrderBookDelta, OrderBookLevel
from services.market_ingestion.kline_validator import KlineBar
from services.shared.contracts.message_envelope import EnvelopeValidationError


class _FakePublisher:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def publish(self, *, routing_key: str, message: dict) -> None:
        self.messages.append({"routing_key": routing_key, "message": message})


def _sample_delta() -> OrderBookDelta:
    return OrderBookDelta(
        exchange="binance",
        symbol="BTC/USDT",
        sequence_start=201,
        sequence_end=202,
        timestamp_ms=1739535602000,
        bids=(OrderBookLevel(42000.0, 1.4),),
        asks=(OrderBookLevel(42001.0, 1.3),),
    )


@pytest.mark.asyncio
async def test_publish_order_book_delta_to_market_canonical() -> None:
    publisher = _FakePublisher()
    pipeline = CanonicalNormalizationPipeline(publisher=publisher)

    envelope = await pipeline.publish_order_book_delta(_sample_delta(), mode="MOCK")

    assert envelope["event_type"] == "market.canonical.orderbook_delta"
    assert publisher.messages[0]["routing_key"] == "market.canonical"
    assert publisher.messages[0]["message"]["payload"]["symbol"] == "BTC/USDT"
    assert "idempotency_key" in envelope


@pytest.mark.asyncio
async def test_publish_kline_validation_result_to_market_canonical() -> None:
    publisher = _FakePublisher()
    pipeline = CanonicalNormalizationPipeline(publisher=publisher)

    bar = KlineBar(1700000000000, 10.0, 11.0, 9.5, 10.8, 100.0)
    envelope = await pipeline.publish_kline_validation(
        exchange="binance",
        symbol="BTC/USDT",
        interval_ms=60_000,
        bars=[bar],
        mode="REAL",
    )

    assert envelope["event_type"] == "market.canonical.kline_validation"
    assert publisher.messages[0]["message"]["mode"] == "REAL"
    assert publisher.messages[0]["message"]["payload"]["validation"]["is_valid"] is True


@pytest.mark.asyncio
async def test_pipeline_rejects_invalid_mode() -> None:
    publisher = _FakePublisher()
    pipeline = CanonicalNormalizationPipeline(publisher=publisher)

    with pytest.raises(EnvelopeValidationError):
        await pipeline.publish_order_book_delta(_sample_delta(), mode="PAPER")
