from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode
import httpx
import asyncio
import json
import time


class BinanceHTTPAdapterError(RuntimeError):
    """Raised when Binance depth endpoint cannot be consumed safely."""


class BinanceHTTPOrderBookClient:
    """Concrete REST/polling adapter compatible with CCXTIngestionAdapter protocols."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.binance.com",
        depth_path: str = "/api/v3/depth",
        klines_path: str = "/api/v3/klines",
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.depth_path = depth_path
        self.klines_path = klines_path
        self.timeout_seconds = timeout_seconds

    async def fetch_order_book(self, symbol: str, limit: int | None = None) -> Mapping[str, Any]:
        return await asyncio.to_thread(self._request_depth, symbol, limit)

    async def watch_order_book(self, symbol: str, limit: int | None = None) -> Mapping[str, Any]:
        return await asyncio.to_thread(self._request_depth, symbol, limit)

    async def fetch_klines(
        self,
        symbol: str,
        *,
        interval: str,
        limit: int = 200,
    ) -> tuple[dict[str, Any], ...]:
        return await asyncio.to_thread(self._request_klines, symbol, interval, limit)

    def _request_depth(self, symbol: str, limit: int | None) -> Mapping[str, Any]:
        exchange_symbol = symbol.replace("/", "").upper()
        query = {"symbol": exchange_symbol}
        if limit is not None:
            query["limit"] = int(limit)
        url = f"{self.base_url}{self.depth_path}?{urlencode(query)}"

        try:
            with httpx.Client(timeout=self.timeout_seconds, verify=True) as client:
                response = client.get(url)
                response.raise_for_status()
                raw = response.text
        except httpx.HTTPStatusError as exc:  # pragma: no cover - tested through monkeypatch
            detail = exc.response.text
            raise BinanceHTTPAdapterError(f"Binance HTTP {exc.response.status_code}: {detail}") from exc
        except httpx.HTTPError as exc:  # pragma: no cover - tested through monkeypatch
            raise BinanceHTTPAdapterError(f"Binance connection error: {exc}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BinanceHTTPAdapterError("Binance depth response is not valid JSON") from exc

        if not isinstance(parsed, Mapping):
            raise BinanceHTTPAdapterError("Binance depth response must be a JSON object")
        if "bids" not in parsed or "asks" not in parsed:
            raise BinanceHTTPAdapterError("Binance depth response must include bids and asks")

        return {
            "nonce": int(parsed.get("lastUpdateId", 0) or 0),
            "timestamp": int(time.time() * 1000),
            "bids": list(parsed.get("bids", [])),
            "asks": list(parsed.get("asks", [])),
        }

    def _request_klines(self, symbol: str, interval: str, limit: int) -> tuple[dict[str, Any], ...]:
        exchange_symbol = symbol.replace("/", "").upper()
        query = {
            "symbol": exchange_symbol,
            "interval": interval.strip() or "1m",
            "limit": max(1, int(limit)),
        }
        url = f"{self.base_url}{self.klines_path}?{urlencode(query)}"
        parsed = _request_json(url=url, timeout_seconds=self.timeout_seconds)
        if not isinstance(parsed, list):
            raise BinanceHTTPAdapterError("Binance kline response must be a JSON array")

        bars: list[dict[str, Any]] = []
        for item in parsed:
            if not isinstance(item, list) or len(item) < 9:
                continue
            try:
                bars.append(
                    {
                        "open_time_ms": int(item[0]),
                        "open": float(item[1]),
                        "high": float(item[2]),
                        "low": float(item[3]),
                        "close": float(item[4]),
                        "volume": float(item[5]),
                        "quote_volume": float(item[7]),
                        "trades": int(item[8]),
                    }
                )
            except (TypeError, ValueError):
                continue
        bars.sort(key=lambda row: int(row["open_time_ms"]))
        return tuple(bars)


def _request_json(*, url: str, timeout_seconds: float) -> Any:
    try:
        with httpx.Client(timeout=timeout_seconds, verify=True) as client:
            response = client.get(url)
            response.raise_for_status()
            raw = response.text
    except httpx.HTTPStatusError as exc:  # pragma: no cover - tested through monkeypatch
        detail = exc.response.text
        raise BinanceHTTPAdapterError(f"Binance HTTP {exc.response.status_code}: {detail}") from exc
    except httpx.HTTPError as exc:  # pragma: no cover - tested through monkeypatch
        raise BinanceHTTPAdapterError(f"Binance connection error: {exc}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BinanceHTTPAdapterError("Binance response is not valid JSON") from exc
