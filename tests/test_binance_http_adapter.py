from __future__ import annotations

from typing import Any
import json

import pytest

from services.market_ingestion.binance_http_adapter import BinanceHTTPAdapterError, BinanceHTTPOrderBookClient


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        _ = exc_type, exc, tb
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


@pytest.mark.asyncio
async def test_binance_http_adapter_fetches_and_normalizes_depth_payload(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return _FakeResponse(
            {
                "lastUpdateId": 123456,
                "bids": [["42000.0", "1.2"]],
                "asks": [["42001.0", "0.8"]],
            }
        )

    monkeypatch.setattr("services.market_ingestion.binance_http_adapter.urlopen", _fake_urlopen)

    client = BinanceHTTPOrderBookClient(base_url="https://api.binance.com", timeout_seconds=3.0)
    payload = await client.fetch_order_book("BTC/USDT", limit=5)

    assert "symbol=BTCUSDT" in captured["url"]
    assert "limit=5" in captured["url"]
    assert captured["timeout"] == 3.0
    assert payload["nonce"] == 123456
    assert payload["bids"][0][0] == "42000.0"


@pytest.mark.asyncio
async def test_binance_http_adapter_rejects_invalid_payload(monkeypatch) -> None:
    def _fake_urlopen(request, timeout):
        _ = request, timeout
        return _FakeResponse({"lastUpdateId": 1})

    monkeypatch.setattr("services.market_ingestion.binance_http_adapter.urlopen", _fake_urlopen)

    client = BinanceHTTPOrderBookClient()
    with pytest.raises(BinanceHTTPAdapterError):
        await client.watch_order_book("BTC/USDT", limit=5)
