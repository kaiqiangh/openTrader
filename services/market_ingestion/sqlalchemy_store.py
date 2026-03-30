from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import json
import sqlite3

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine


class SQLiteTimeseriesStore:
    """Concrete timeseries store supporting sqlite and SQLAlchemy Engine bindings."""

    def __init__(self, *, connection: sqlite3.Connection | Engine | Connection) -> None:
        self._sqlite_connection: sqlite3.Connection | None = None
        self._engine: Engine | None = None
        if isinstance(connection, sqlite3.Connection):
            self._sqlite_connection = connection
            return
        if isinstance(connection, Engine):
            self._engine = connection
            return
        if isinstance(connection, Connection):
            self._engine = connection.engine
            return
        raise TypeError(
            "connection must be sqlite3.Connection, sqlalchemy.Engine, or sqlalchemy.Connection"
        )

    async def upsert_orderbook_snapshot(self, row: dict[str, Any]) -> None:
        snapshot_time = _as_iso(row.get("snapshot_time")) or _utc_now_iso()
        best_bid = _to_float(row.get("best_bid"), default=0.0)
        best_ask = _to_float(row.get("best_ask"), default=0.0)
        spread_bps = _to_float(row.get("spread_bps"), default=0.0)

        self._execute(
            """
            INSERT INTO orderbook_snapshots
                (snapshot_time, exchange, symbol, bids, asks, best_bid, best_ask, spread_bps)
            VALUES
                (:snapshot_time, :exchange, :symbol, :bids, :asks, :best_bid, :best_ask, :spread_bps)
            ON CONFLICT (snapshot_time, exchange, symbol)
            DO UPDATE SET
                bids = excluded.bids,
                asks = excluded.asks,
                best_bid = excluded.best_bid,
                best_ask = excluded.best_ask,
                spread_bps = excluded.spread_bps
            """,
            {
                "snapshot_time": snapshot_time,
                "exchange": str(row["exchange"]),
                "symbol": str(row["symbol"]),
                "bids": json.dumps(row.get("bids", []), ensure_ascii=True),
                "asks": json.dumps(row.get("asks", []), ensure_ascii=True),
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread_bps": spread_bps,
            },
        )

    async def upsert_kline(self, row: dict[str, Any]) -> None:
        interval = _normalize_interval(row)
        open_time = (
            _as_iso(row.get("open_time")) or _as_iso(row.get("open_time_ms")) or _utc_now_iso()
        )

        self._execute(
            """
            INSERT INTO klines
                (time, exchange, symbol, "interval", open, high, low, close, volume, quote_volume, trades)
            VALUES
                (:time, :exchange, :symbol, :interval, :open, :high, :low, :close, :volume, :quote_volume, :trades)
            ON CONFLICT (time, exchange, symbol, "interval")
            DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume,
                quote_volume = excluded.quote_volume,
                trades = excluded.trades
            """,
            {
                "time": open_time,
                "exchange": str(row["exchange"]),
                "symbol": str(row["symbol"]),
                "interval": interval,
                "open": _to_float(row.get("open"), default=0.0),
                "high": _to_float(row.get("high"), default=0.0),
                "low": _to_float(row.get("low"), default=0.0),
                "close": _to_float(row.get("close"), default=0.0),
                "volume": _to_float(row.get("volume"), default=0.0),
                "quote_volume": _to_float(row.get("quote_volume"), default=0.0),
                "trades": int(row.get("trades", 0) or 0),
            },
        )

    def _execute(self, statement: str, params: dict[str, Any]) -> None:
        if self._sqlite_connection is not None:
            self._sqlite_connection.execute(statement, params)
            self._sqlite_connection.commit()
            return
        if self._engine is None:
            raise RuntimeError("timeseries store was not initialized with a valid connection")
        with self._engine.begin() as connection:
            connection.execute(text(statement), params)


# Backward-compatible alias for previous contract naming.
SQLAlchemyTimeseriesStore = SQLiteTimeseriesStore


def _normalize_interval(row: dict[str, Any]) -> str:
    if isinstance(row.get("interval"), str) and row["interval"].strip():
        return str(row["interval"])

    interval_ms = row.get("interval_ms")
    if interval_ms is None:
        return "1m"
    ms_value = int(interval_ms)
    if ms_value == 60_000:
        return "1m"
    if ms_value == 300_000:
        return "5m"
    if ms_value == 900_000:
        return "15m"
    if ms_value == 3_600_000:
        return "1h"
    return f"{ms_value}ms"


def _as_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value
    try:
        timestamp_ms = int(value)
    except (TypeError, ValueError):
        return None
    dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _to_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
