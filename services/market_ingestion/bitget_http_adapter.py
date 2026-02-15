from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import asyncio
import json
import time


class BitgetHTTPAdapterError(RuntimeError):
    """Raised when Bitget depth endpoint cannot be consumed safely."""


class BitgetHTTPOrderBookClient:
    """Concrete REST/polling adapter compatible with CCXTIngestionAdapter protocols."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.bitget.com",
        depth_path: str = "/api/v2/spot/market/orderbook",
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
            raise BitgetHTTPAdapterError(f"Bitget HTTP {exc.code}: {detail}") from exc
        except URLError as exc:  # pragma: no cover - tested through monkeypatch
            raise BitgetHTTPAdapterError(f"Bitget connection error: {exc.reason}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BitgetHTTPAdapterError("Bitget depth response is not valid JSON") from exc

        if not isinstance(parsed, Mapping):
            raise BitgetHTTPAdapterError("Bitget depth response must be a JSON object")
        if str(parsed.get("code", "")).strip() not in {"", "00000", "0"}:
            raise BitgetHTTPAdapterError(f"Bitget depth response returned error code: {parsed.get('code')}")

        raw_data = parsed.get("data")
        if isinstance(raw_data, list):
            if not raw_data:
                raise BitgetHTTPAdapterError("Bitget depth response data list is empty")
            data = raw_data[0]
        else:
            data = raw_data
        if not isinstance(data, Mapping):
            raise BitgetHTTPAdapterError("Bitget depth response data must be an object")

        bids = data.get("bids")
        asks = data.get("asks")
        if not isinstance(bids, list) or not isinstance(asks, list):
            raise BitgetHTTPAdapterError("Bitget depth response must include list bids and asks")

        timestamp = _parse_int(data.get("ts"))
        if timestamp is None:
            timestamp = _parse_int(parsed.get("requestTime"))
        if timestamp is None:
            timestamp = int(time.time() * 1000)

        nonce = _parse_int(data.get("version")) or timestamp
        return {
            "nonce": nonce,
            "timestamp": timestamp,
            "bids": list(bids),
            "asks": list(asks),
        }


def _parse_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
