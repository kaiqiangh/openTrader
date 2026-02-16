from __future__ import annotations

from typing import Any
import json

import pytest

from services.market_ingestion.bitget_http_adapter import BitgetHTTPAdapterError, BitgetHTTPOrderBookClient


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
async def test_bitget_http_adapter_fetches_and_normalizes_depth_payload(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return _FakeResponse(
            {
                "code": "00000",
                "msg": "success",
                "requestTime": 1739535602000,
                "data": {
                    "bids": [["42000.5", "1.1"]],
                    "asks": [["42001.2", "0.7"]],
                    "ts": "1739535602100",
                },
            }
        )

    monkeypatch.setattr("services.market_ingestion.bitget_http_adapter.urlopen", _fake_urlopen)

    client = BitgetHTTPOrderBookClient(base_url="https://api.bitget.com", timeout_seconds=4.0)
    payload = await client.fetch_order_book("BTC/USDT", limit=15)

    assert "symbol=BTCUSDT" in captured["url"]
    assert "limit=15" in captured["url"]
    assert captured["timeout"] == 4.0
    assert payload["bids"][0][0] == "42000.5"
    assert payload["asks"][0][0] == "42001.2"
    assert payload["timestamp"] == 1739535602100


@pytest.mark.asyncio
async def test_bitget_http_adapter_rejects_invalid_payload(monkeypatch) -> None:
    def _fake_urlopen(request, timeout):
        _ = request, timeout
        return _FakeResponse({"code": "00000", "data": {"bids": []}})

    monkeypatch.setattr("services.market_ingestion.bitget_http_adapter.urlopen", _fake_urlopen)

    client = BitgetHTTPOrderBookClient()
    with pytest.raises(BitgetHTTPAdapterError):
        await client.watch_order_book("BTC/USDT", limit=5)


@pytest.mark.asyncio
async def test_bitget_http_adapter_fetches_klines(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return _FakeResponse(
            {
                "code": "00000",
                "msg": "success",
                "data": [
                    ["1739535660000", "42005.0", "42015.0", "42000.0", "42012.0", "11.0", "462000.0", "462000.0"],
                    ["1739535600000", "42000.0", "42010.0", "41990.0", "42005.0", "12.5", "525000.0", "525000.0"],
                ],
            }
        )

    monkeypatch.setattr("services.market_ingestion.bitget_http_adapter.urlopen", _fake_urlopen)

    client = BitgetHTTPOrderBookClient(base_url="https://api.bitget.com", timeout_seconds=4.0)
    bars = await client.fetch_klines("BTC/USDT", interval="1m", limit=2)

    assert "symbol=BTCUSDT" in captured["url"]
    assert "granularity=1min" in captured["url"]
    assert "limit=2" in captured["url"]
    assert captured["timeout"] == 4.0
    assert len(bars) == 2
    assert bars[0]["open_time_ms"] == 1739535600000
    assert bars[0]["open"] == 42000.0
    assert bars[1]["close"] == 42012.0
    assert bars[0]["trades"] == 0
