from __future__ import annotations

from typing import Any
import json

import httpx
import pytest

from services.market_ingestion.binance_http_adapter import BinanceHTTPAdapterError, BinanceHTTPOrderBookClient


class _FakeHTTPResponse:
    def __init__(self, payload: Any) -> None:
        self.text = json.dumps(payload)
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass


class _FakeClient:
    def __init__(self, timeout, verify, response: _FakeHTTPResponse, captured: dict[str, Any]) -> None:
        self._response = response
        self._captured = captured
        self._timeout = timeout
        self._verify = verify

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str, **kwargs: Any) -> _FakeHTTPResponse:
        self._captured["url"] = url
        self._captured["timeout"] = self._timeout
        return self._response

    def request(self, method: str, url: str, **kwargs: Any) -> _FakeHTTPResponse:
        self._captured["url"] = url
        self._captured["method"] = method
        self._captured["timeout"] = self._timeout
        return self._response


@pytest.mark.asyncio
async def test_binance_http_adapter_fetches_and_normalizes_depth_payload(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    response = _FakeHTTPResponse(
        {
            "lastUpdateId": 123456,
            "bids": [["42000.0", "1.2"]],
            "asks": [["42001.0", "0.8"]],
        }
    )

    def _fake_client_init(timeout, verify):
        return _FakeClient(timeout, verify, response, captured)

    class _FakeClientCls:
        def __init__(self, **kwargs):
            self._inner = _fake_client_init(kwargs.get("timeout"), kwargs.get("verify"))

        def __enter__(self):
            return self._inner

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(httpx, "Client", _FakeClientCls)

    client = BinanceHTTPOrderBookClient(base_url="https://api.binance.com", timeout_seconds=3.0)
    payload = await client.fetch_order_book("BTC/USDT", limit=5)

    assert "symbol=BTCUSDT" in captured["url"]
    assert "limit=5" in captured["url"]
    assert captured["timeout"] == 3.0
    assert payload["nonce"] == 123456
    assert payload["bids"][0][0] == "42000.0"


@pytest.mark.asyncio
async def test_binance_http_adapter_rejects_invalid_payload(monkeypatch) -> None:
    response = _FakeHTTPResponse({"lastUpdateId": 1})

    class _FakeClientCls:
        def __init__(self, **kwargs):
            self._inner = _FakeClient(kwargs.get("timeout"), kwargs.get("verify"), response, {})

        def __enter__(self):
            return self._inner

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(httpx, "Client", _FakeClientCls)

    client = BinanceHTTPOrderBookClient()
    with pytest.raises(BinanceHTTPAdapterError):
        await client.watch_order_book("BTC/USDT", limit=5)


@pytest.mark.asyncio
async def test_binance_http_adapter_fetches_klines(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    response = _FakeHTTPResponse(
        [
            [1739535600000, "42000.0", "42010.0", "41990.0", "42005.0", "12.5", 1739535659999, "525000.0", 120],
            [1739535660000, "42005.0", "42015.0", "42000.0", "42012.0", "11.0", 1739535719999, "462000.0", 110],
        ]
    )

    class _FakeClientCls:
        def __init__(self, **kwargs):
            self._inner = _FakeClient(kwargs.get("timeout"), kwargs.get("verify"), response, captured)

        def __enter__(self):
            return self._inner

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(httpx, "Client", _FakeClientCls)

    client = BinanceHTTPOrderBookClient(base_url="https://api.binance.com", timeout_seconds=3.0)
    bars = await client.fetch_klines("BTC/USDT", interval="1m", limit=2)

    assert "symbol=BTCUSDT" in captured["url"]
    assert "interval=1m" in captured["url"]
    assert "limit=2" in captured["url"]
    assert captured["timeout"] == 3.0
    assert len(bars) == 2
    assert bars[0]["open_time_ms"] == 1739535600000
    assert bars[0]["open"] == 42000.0
    assert bars[1]["close"] == 42012.0
