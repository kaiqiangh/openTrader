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
