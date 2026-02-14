from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol, Sequence

from services.market_ingestion.contracts import OrderBookSnapshot
from services.market_ingestion.kline_validator import KlineBar


class TimeseriesStore(Protocol):
    async def upsert_orderbook_snapshot(self, row: dict[str, Any]) -> None: ...

    async def upsert_kline(self, row: dict[str, Any]) -> None: ...


class TimescalePersistenceWriters:
    def __init__(self, *, store: TimeseriesStore) -> None:
        self.store = store

    async def persist_orderbook_snapshot(self, snapshot: OrderBookSnapshot) -> dict[str, Any]:
        best_bid = snapshot.bids[0].price if snapshot.bids else None
        best_ask = snapshot.asks[0].price if snapshot.asks else None
        spread_bps = _spread_bps(best_bid=best_bid, best_ask=best_ask)

        row = {
            "table": "orderbook_snapshots",
            "exchange": snapshot.exchange,
            "symbol": snapshot.symbol,
            "sequence": snapshot.sequence,
            "snapshot_time": _as_utc_iso(snapshot.timestamp_ms),
            "bids": [{"price": level.price, "amount": level.amount} for level in snapshot.bids],
            "asks": [{"price": level.price, "amount": level.amount} for level in snapshot.asks],
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread_bps": spread_bps,
        }
        await self.store.upsert_orderbook_snapshot(row)
        return row

    async def persist_klines(
        self,
        *,
        exchange: str,
        symbol: str,
        interval_ms: int,
        bars: Sequence[KlineBar],
    ) -> int:
        deduped: dict[int, KlineBar] = {}
        for bar in bars:
            deduped[bar.open_time_ms] = bar

        written = 0
        for open_time_ms in sorted(deduped):
            bar = deduped[open_time_ms]
            row = {
                "table": "klines",
                "exchange": exchange,
                "symbol": symbol,
                "interval_ms": interval_ms,
                "open_time_ms": bar.open_time_ms,
                "open_time": _as_utc_iso(bar.open_time_ms),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            await self.store.upsert_kline(row)
            written += 1
        return written


def _as_utc_iso(timestamp_ms: int | None) -> str | None:
    if timestamp_ms is None:
        return None
    dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _spread_bps(*, best_bid: float | None, best_ask: float | None) -> float | None:
    if best_bid is None or best_ask is None or best_bid <= 0:
        return None
    return ((best_ask - best_bid) / best_bid) * 10_000
