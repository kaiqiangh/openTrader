from __future__ import annotations

from typing import Any

import pytest

from services.market_ingestion.ccxt_pro_adapter import CCXTProOrderBookClient


class _FakeRestClient:
    async def fetch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, Any]:
        return {
            "nonce": 10,
            "timestamp": 1739535600000,
            "bids": [[50000.0, 1.0]],
            "asks": [[50001.0, 1.1]],
        }

    async def fetch_klines(
        self, symbol: str, *, interval: str, limit: int = 200
    ) -> tuple[dict[str, Any], ...]:
        return (
            {
                "open_time_ms": 1739535600000,
                "open": 50000.0,
                "high": 50100.0,
                "low": 49950.0,
                "close": 50050.0,
                "volume": 2.5,
                "quote_volume": 125125.0,
                "trades": 12,
            },
        )


class _FakeWsClient:
    async def watch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, Any]:
        return {
            "U": 11,
            "u": 11,
            "timestamp": 1739535601000,
            "bids": [[50000.5, 0.9]],
            "asks": [[50001.5, 1.0]],
        }


@pytest.mark.asyncio
async def test_ccxt_pro_adapter_falls_back_to_direct_clients_when_library_missing(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "importlib.import_module", lambda name: (_ for _ in ()).throw(ImportError("missing"))
    )
    client = CCXTProOrderBookClient(
        exchange="binance",
        fallback_rest_client=_FakeRestClient(),
        fallback_ws_client=_FakeWsClient(),
    )

    snapshot = await client.fetch_order_book("BTC/USDT", limit=5)
    delta = await client.watch_order_book("BTC/USDT", limit=5)
    klines = await client.fetch_klines("BTC/USDT", interval="1m", limit=10)

    assert snapshot["nonce"] == 10
    assert delta["u"] == 11
    assert len(klines) == 1
    assert klines[0]["close"] == 50050.0
