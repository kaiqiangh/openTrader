from __future__ import annotations

import pytest

from services.market_ingestion.exchange_adapter import (
    AdapterPayloadError,
    CCXTIngestionAdapter,
)


class _FakeRestClient:
    async def fetch_order_book(self, symbol: str, limit: int | None = None) -> dict:
        assert symbol == "BTC/USDT"
        assert limit == 5
        return {
            "nonce": 101,
            "timestamp": 1739535600000,
            "bids": [[42001.0, 2.0], [42003.0, 1.5]],
            "asks": [[42005.0, 1.2], [42004.0, 0.8]],
        }


class _FakeWsClient:
    async def watch_order_book(self, symbol: str, limit: int | None = None) -> dict:
        assert symbol == "BTC/USDT"
        assert limit == 5
        return {
            "U": 102,
            "u": 103,
            "timestamp": 1739535601000,
            "bids": [[42003.0, 1.2], [42000.0, 0.0]],
            "asks": [[42004.0, 1.0]],
        }


class _RestOnlyClient:
    def __init__(self) -> None:
        self.fetch_calls = 0

    async def fetch_order_book(self, symbol: str, limit: int | None = None) -> dict:
        assert symbol == "BTC/USDT"
        assert limit == 5
        self.fetch_calls += 1
        return {
            "nonce": 205,
            "timestamp": 1739535602000,
            "bids": [[42002.0, 1.5], [42001.5, 0.4]],
            "asks": [[42002.5, 1.0], [42003.0, 0.7]],
        }


class _FailingWsClient:
    async def watch_order_book(self, symbol: str, limit: int | None = None) -> dict:
        raise AssertionError(f"ws client should not be called for rest fetch mode: {symbol} {limit}")


@pytest.mark.asyncio
async def test_bootstrap_snapshot_normalizes_levels() -> None:
    adapter = CCXTIngestionAdapter(
        exchange="binance",
        rest_client=_FakeRestClient(),
        ws_client=_FakeWsClient(),
    )
    snapshot = await adapter.bootstrap_snapshot("BTC/USDT", limit=5)

    assert snapshot.exchange == "binance"
    assert snapshot.symbol == "BTC/USDT"
    assert snapshot.sequence == 101
    assert snapshot.bids[0].price == 42003.0
    assert snapshot.asks[0].price == 42004.0


@pytest.mark.asyncio
async def test_poll_delta_reads_sequence_window() -> None:
    adapter = CCXTIngestionAdapter(
        exchange="binance",
        rest_client=_FakeRestClient(),
        ws_client=_FakeWsClient(),
    )
    delta = await adapter.poll_delta("BTC/USDT", limit=5)

    assert delta.sequence_start == 102
    assert delta.sequence_end == 103
    assert delta.bids[1].amount == 0.0


@pytest.mark.asyncio
async def test_poll_delta_uses_rest_source_when_configured() -> None:
    rest = _RestOnlyClient()
    adapter = CCXTIngestionAdapter(
        exchange="binance",
        rest_client=rest,
        ws_client=_FailingWsClient(),
        delta_source="rest",
    )

    delta = await adapter.poll_delta("BTC/USDT", limit=5)

    assert rest.fetch_calls == 1
    assert delta.sequence_start == 205
    assert delta.sequence_end == 205
    assert delta.bids[0].price == 42002.0
    assert delta.asks[0].price == 42002.5


@pytest.mark.asyncio
async def test_poll_delta_source_override_uses_rest_even_if_websocket_default() -> None:
    rest = _RestOnlyClient()
    adapter = CCXTIngestionAdapter(
        exchange="binance",
        rest_client=rest,
        ws_client=_FailingWsClient(),
        delta_source="websocket",
    )

    delta = await adapter.poll_delta("BTC/USDT", limit=5, source_override="rest")

    assert rest.fetch_calls == 1
    assert delta.sequence_start == 205
    assert delta.sequence_end == 205


@pytest.mark.asyncio
async def test_bootstrap_snapshot_rejects_invalid_payload() -> None:
    class _BadRestClient:
        async def fetch_order_book(self, symbol: str, limit: int | None = None) -> dict:
            return {"nonce": 7, "asks": []}

    adapter = CCXTIngestionAdapter(
        exchange="binance",
        rest_client=_BadRestClient(),
        ws_client=_FakeWsClient(),
    )

    with pytest.raises(AdapterPayloadError):
        await adapter.bootstrap_snapshot("BTC/USDT", limit=5)
