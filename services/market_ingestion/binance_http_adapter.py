from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
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
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.depth_path = depth_path
        self.timeout_seconds = timeout_seconds

    async def fetch_order_book(self, symbol: str, limit: int | None = None) -> Mapping[str, Any]:
        return await asyncio.to_thread(self._request_depth, symbol, limit)

    async def watch_order_book(self, symbol: str, limit: int | None = None) -> Mapping[str, Any]:
        return await asyncio.to_thread(self._request_depth, symbol, limit)

    def _request_depth(self, symbol: str, limit: int | None) -> Mapping[str, Any]:
        exchange_symbol = symbol.replace("/", "").upper()
        query = {"symbol": exchange_symbol}
        if limit is not None:
            query["limit"] = int(limit)
        url = f"{self.base_url}{self.depth_path}?{urlencode(query)}"

        request = Request(url=url, method="GET")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - explicit URL target
                raw = response.read().decode("utf-8")
        except HTTPError as exc:  # pragma: no cover - tested through monkeypatch
            detail = exc.read().decode("utf-8") if hasattr(exc, "read") else str(exc)
            raise BinanceHTTPAdapterError(f"Binance HTTP {exc.code}: {detail}") from exc
        except URLError as exc:  # pragma: no cover - tested through monkeypatch
            raise BinanceHTTPAdapterError(f"Binance connection error: {exc.reason}") from exc

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
