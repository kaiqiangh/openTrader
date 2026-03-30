from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
import importlib

_logger = logging.getLogger(__name__)


class CCXTProAdapterError(RuntimeError):
    """Raised when CCXT Pro client initialization or API calls fail."""


class CCXTProOrderBookClient:
    """CCXT Pro client wrapper with resilient fallback to existing direct adapters."""

    def __init__(
        self,
        *,
        exchange: str,
        fallback_rest_client: Any,
        fallback_ws_client: Any,
        timeout_ms: int = 10_000,
    ) -> None:
        normalized_exchange = exchange.strip().lower()
        if not normalized_exchange:
            raise ValueError("exchange must be non-empty")

        self.exchange = normalized_exchange
        self.timeout_ms = max(1000, int(timeout_ms))
        self.fallback_rest_client = fallback_rest_client
        self.fallback_ws_client = fallback_ws_client
        self._client: Any | None = None
        self._init_error: str | None = None

        try:
            module = importlib.import_module("ccxt.pro")
            exchange_factory = getattr(module, normalized_exchange, None)
            if exchange_factory is None:
                raise CCXTProAdapterError(f"ccxt.pro exchange not found: {normalized_exchange}")
            self._client = exchange_factory(
                {
                    "enableRateLimit": True,
                    "timeout": self.timeout_ms,
                }
            )
        except Exception as exc:  # noqa: BLE001 - fallback mode captures all init failures
            self._client = None
            self._init_error = f"{exc.__class__.__name__}: {exc}"

    @property
    def using_ccxt_pro(self) -> bool:
        return self._client is not None

    @property
    def init_error(self) -> str | None:
        return self._init_error

    async def fetch_order_book(self, symbol: str, limit: int | None = None) -> Mapping[str, Any]:
        if self._client is not None:
            try:
                return await self._client.fetch_order_book(symbol, limit)
            except Exception:
                _logger.warning("ccxt_pro_fetch_order_book_fallback", exc_info=True)
        return await self.fallback_rest_client.fetch_order_book(symbol, limit=limit)

    async def watch_order_book(self, symbol: str, limit: int | None = None) -> Mapping[str, Any]:
        if self._client is not None:
            try:
                return await self._client.watch_order_book(symbol, limit)
            except Exception:
                _logger.warning("ccxt_pro_watch_order_book_fallback", exc_info=True)
        return await self.fallback_ws_client.watch_order_book(symbol, limit=limit)

    async def fetch_klines(
        self,
        symbol: str,
        *,
        interval: str,
        limit: int = 200,
    ) -> tuple[dict[str, Any], ...]:
        if self._client is not None:
            try:
                rows = await self._client.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
                if isinstance(rows, list):
                    normalized = [_normalize_ohlcv_row(item) for item in rows]
                    return tuple(r for r in normalized if r is not None)
            except Exception:
                _logger.warning("ccxt_pro_fetch_ohlcv_fallback", exc_info=True)
        fallback = await self.fallback_rest_client.fetch_klines(symbol, interval=interval, limit=limit)
        return tuple(dict(item) for item in fallback)

    async def close(self) -> None:
        if self._client is None:
            return
        close_fn = getattr(self._client, "close", None)
        if close_fn is None:
            return
        try:
            await close_fn()
        except Exception:
            return


def _normalize_ohlcv_row(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, list) or len(row) < 6:
        return None
    open_time_ms = int(row[0])
    open_price = float(row[1])
    high_price = float(row[2])
    low_price = float(row[3])
    close_price = float(row[4])
    volume = float(row[5])
    return {
        "open_time_ms": open_time_ms,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "volume": volume,
        "quote_volume": volume * close_price,
        "trades": 0,
    }
