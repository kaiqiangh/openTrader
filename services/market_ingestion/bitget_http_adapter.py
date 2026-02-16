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
        klines_path: str = "/api/v2/spot/market/candles",
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

    def _request_klines(self, symbol: str, interval: str, limit: int) -> tuple[dict[str, Any], ...]:
        exchange_symbol = symbol.replace("/", "").upper()
        granularity = _normalize_bitget_granularity(interval)
        query = {
            "symbol": exchange_symbol,
            "granularity": granularity,
            "limit": max(1, int(limit)),
        }
        url = f"{self.base_url}{self.klines_path}?{urlencode(query)}"
        parsed = _request_json(url=url, timeout_seconds=self.timeout_seconds)

        if not isinstance(parsed, Mapping):
            raise BitgetHTTPAdapterError("Bitget kline response must be a JSON object")
        if str(parsed.get("code", "")).strip() not in {"", "00000", "0"}:
            raise BitgetHTTPAdapterError(f"Bitget kline response returned error code: {parsed.get('code')}")
        rows = parsed.get("data")
        if not isinstance(rows, list):
            raise BitgetHTTPAdapterError("Bitget kline response data must be a list")

        bars: list[dict[str, Any]] = []
        for item in rows:
            if not isinstance(item, list) or len(item) < 7:
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
                        "quote_volume": float(item[6]),
                        "trades": int(item[7]) if len(item) > 7 else 0,
                    }
                )
            except (TypeError, ValueError):
                continue
        bars.sort(key=lambda row: int(row["open_time_ms"]))
        return tuple(bars)


def _request_json(*, url: str, timeout_seconds: float) -> Any:
    request = Request(url=url, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - explicit URL target
            raw = response.read().decode("utf-8")
    except HTTPError as exc:  # pragma: no cover - tested through monkeypatch
        detail = exc.read().decode("utf-8") if hasattr(exc, "read") else str(exc)
        raise BitgetHTTPAdapterError(f"Bitget HTTP {exc.code}: {detail}") from exc
    except URLError as exc:  # pragma: no cover - tested through monkeypatch
        raise BitgetHTTPAdapterError(f"Bitget connection error: {exc.reason}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BitgetHTTPAdapterError("Bitget response is not valid JSON") from exc


def _normalize_bitget_granularity(interval: str) -> str:
    normalized = interval.strip().lower()
    mapping = {
        "1m": "1min",
        "3m": "3min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
        "4h": "4h",
        "6h": "6h",
        "12h": "12h",
        "1d": "1day",
    }
    return mapping.get(normalized, normalized or "1min")


def _parse_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
