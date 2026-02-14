from __future__ import annotations

import pytest

from services.market_ingestion.contracts import OrderBookDelta, OrderBookLevel
from services.market_ingestion.integration_harness import IngestionIntegrationHarness


def _fixture() -> list[OrderBookDelta]:
    return [
        OrderBookDelta(
            exchange="binance",
            symbol="BTC/USDT",
            sequence_start=401,
            sequence_end=401,
            timestamp_ms=1739535604000,
            bids=(OrderBookLevel(42000.0, 1.4),),
            asks=(OrderBookLevel(42001.0, 1.3),),
        ),
        OrderBookDelta(
            exchange="binance",
            symbol="BTC/USDT",
            sequence_start=402,
            sequence_end=402,
            timestamp_ms=1739535605000,
            bids=(OrderBookLevel(42000.0, 1.2),),
            asks=(OrderBookLevel(42001.0, 1.1),),
        ),
    ]


@pytest.mark.asyncio
async def test_replay_harness_returns_messages_and_digest() -> None:
    harness = IngestionIntegrationHarness()
    result = await harness.replay_orderbook_fixture(_fixture(), mode="MOCK")

    assert len(result.messages) == 2
    assert result.messages[0]["routing_key"] == "market.canonical"
    assert len(result.stable_digest) == 64


@pytest.mark.asyncio
async def test_replay_harness_reports_deterministic_digest() -> None:
    harness = IngestionIntegrationHarness()
    assert await harness.verify_deterministic_orderbook_replay(_fixture(), mode="MOCK") is True


@pytest.mark.asyncio
async def test_replay_digest_changes_when_fixture_changes() -> None:
    harness = IngestionIntegrationHarness()
    first = await harness.replay_orderbook_fixture(_fixture(), mode="MOCK")

    mutated = _fixture()
    mutated[1] = OrderBookDelta(
        exchange="binance",
        symbol="BTC/USDT",
        sequence_start=402,
        sequence_end=402,
        timestamp_ms=1739535605000,
        bids=(OrderBookLevel(42000.0, 2.2),),
        asks=(OrderBookLevel(42001.0, 1.1),),
    )
    second = await harness.replay_orderbook_fixture(mutated, mode="MOCK")

    assert first.stable_digest != second.stable_digest
