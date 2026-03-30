"""Market data worker runner and synthetic clients."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import Any

from services.workers.helpers import _utc_now_ms, _worker_activity_snapshot
from services.workers.runtime_pipeline import MarketRuntimeWorker


def _first_level_price(levels: Any) -> float:
    if not isinstance(levels, list) or not levels:
        return 0.0
    first = levels[0]
    if not isinstance(first, Mapping):
        return 0.0
    return float(first.get("price", 0.0) or 0.0)


def _build_order_book_payload(*, base_price: float, sequence: int, timestamp_ms: int) -> dict[str, Any]:
    bid_0 = round(base_price - 0.5, 4)
    ask_0 = round(base_price + 0.5, 4)
    return {
        "nonce": sequence,
        "U": sequence,
        "u": sequence,
        "timestamp": timestamp_ms,
        "bids": [[bid_0, 5.0], [round(bid_0 - 1.0, 4), 2.5]],
        "asks": [[ask_0, 4.0], [round(ask_0 + 1.0, 4), 2.0]],
    }


def _market_activity_from_envelope(envelope: Mapping[str, Any]) -> dict[str, Any]:
    payload = envelope.get("payload")
    if not isinstance(payload, Mapping):
        return {}
    bids = payload.get("bids")
    asks = payload.get("asks")
    best_bid = _first_level_price(bids)
    best_ask = _first_level_price(asks)
    return {
        "trace_id": str(envelope.get("trace_id", "")),
        "decision_id": str(envelope.get("decision_id", "")),
        "exchange": str(payload.get("exchange", "")),
        "symbol": str(payload.get("symbol", "")),
        "timestamp_ms": payload.get("timestamp_ms"),
        "sequence_start": payload.get("sequence_start"),
        "sequence_end": payload.get("sequence_end"),
        "best_bid": best_bid,
        "best_ask": best_ask,
    }


class _SyntheticRestOrderBookClient:
    def __init__(self, *, base_price: float) -> None:
        self.base_price = max(base_price, 1.0)

    async def fetch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, Any]:
        _ = symbol, limit
        return _build_order_book_payload(
            base_price=self.base_price,
            sequence=1000,
            timestamp_ms=_utc_now_ms(),
        )

    async def fetch_klines(
        self,
        symbol: str,
        *,
        interval: str,
        limit: int = 200,
    ) -> tuple[dict[str, Any], ...]:
        _ = symbol, interval, limit
        now_ms = _utc_now_ms()
        return (
            {
                "open_time_ms": now_ms - 60_000,
                "open": self.base_price - 3.0,
                "high": self.base_price + 8.0,
                "low": self.base_price - 10.0,
                "close": self.base_price + 2.0,
                "volume": 25.0,
                "quote_volume": 25.0 * self.base_price,
                "trades": 80,
            },
        )


class _SyntheticWsOrderBookClient:
    def __init__(self, *, base_price: float) -> None:
        self.base_price = max(base_price, 1.0)
        self._sequence = 1000

    async def watch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, Any]:
        _ = symbol, limit
        self._sequence += 1
        price_shift = ((self._sequence % 6) - 3) * 0.5
        return _build_order_book_payload(
            base_price=self.base_price + price_shift,
            sequence=self._sequence,
            timestamp_ms=_utc_now_ms(),
        )


class MarketWorkerRunner:
    def __init__(
        self,
        *,
        worker: MarketRuntimeWorker,
        min_cycle_interval_seconds: float = 0.0,
    ) -> None:
        self.worker = worker
        self.min_cycle_interval_seconds = max(0.0, float(min_cycle_interval_seconds))
        self._last_run_monotonic: float | None = None
        self._last_activity: dict[str, Any] = {}

    async def run_once(self, *, timeout_seconds: float) -> bool:
        _ = timeout_seconds
        if self._last_run_monotonic is not None and self.min_cycle_interval_seconds > 0:
            elapsed = time.monotonic() - self._last_run_monotonic
            remaining = self.min_cycle_interval_seconds - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)
        cycle_started = time.monotonic()
        try:
            envelope = await self.worker.run_once()
            worker_activity = _worker_activity_snapshot(self.worker)
            if worker_activity:
                self._last_activity = worker_activity
            else:
                self._last_activity = _market_activity_from_envelope(envelope)
        finally:
            # Keep cadence even on transient fetch failures to avoid tight retry loops.
            self._last_run_monotonic = cycle_started
        return True

    def activity_snapshot(self) -> dict[str, Any]:
        return dict(self._last_activity)
