from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
import json
import sqlite3
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from services.market_ingestion.sqlalchemy_store import SQLAlchemyTimeseriesStore
from services.news_ingestion.ingestion_service import NormalizedNewsItem
from services.news_ingestion.tagging_relevance import NewsTag
from services.news_summarizer.summarizer_service import NewsSummaryArtifact
from services.oms.fill_reconciliation import LifecycleEvent, ReconciliationFill, ReconciliationOrder
from services.oms.portfolio_snapshot import PortfolioSnapshot
from services.oms.position_engine import PositionState


class SQLAlchemyRuntimeMarketStore:
    """Market runtime persistence bridge backed by the shared timeseries store."""

    def __init__(self, *, connection: sqlite3.Connection | Engine | Connection) -> None:
        self._timeseries = SQLAlchemyTimeseriesStore(connection=connection)

    async def persist_orderbook_envelope(self, envelope: Mapping[str, Any]) -> None:
        payload = envelope.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("market envelope payload must be a mapping")

        exchange = str(payload.get("exchange", "")).strip()
        symbol = str(payload.get("symbol", "")).strip()
        if not exchange or not symbol:
            raise ValueError("market envelope payload requires exchange and symbol")

        bids = _normalize_levels(payload.get("bids"))
        asks = _normalize_levels(payload.get("asks"))
        best_bid = max((level["price"] for level in bids), default=0.0)
        best_ask_candidates = [level["price"] for level in asks if level["price"] > 0.0]
        best_ask = min(best_ask_candidates, default=0.0)
        spread_bps = _compute_spread_bps(best_bid=best_bid, best_ask=best_ask)
        snapshot_time = _as_iso(payload.get("timestamp_ms")) or _utc_now_iso()

        await self._timeseries.upsert_orderbook_snapshot(
            {
                "snapshot_time": snapshot_time,
                "exchange": exchange,
                "symbol": symbol,
                "bids": bids,
                "asks": asks,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread_bps": spread_bps,
            }
        )

    async def persist_kline_rows(
        self,
        *,
        exchange: str,
        symbol: str,
        interval: str,
        bars: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
    ) -> None:
        normalized_exchange = exchange.strip()
        normalized_symbol = symbol.strip()
        normalized_interval = interval.strip() or "1m"
        if not normalized_exchange or not normalized_symbol:
            raise ValueError("persist_kline_rows requires non-empty exchange and symbol")

        for bar in bars:
            open_time_ms = _to_int(bar.get("open_time_ms"))
            if open_time_ms is None:
                open_time_ms = _to_int(bar.get("open_time"))
            if open_time_ms is None:
                continue
            await self._timeseries.upsert_kline(
                {
                    "exchange": normalized_exchange,
                    "symbol": normalized_symbol,
                    "interval": normalized_interval,
                    "open_time_ms": open_time_ms,
                    "open": _to_float(bar.get("open"), default=0.0),
                    "high": _to_float(bar.get("high"), default=0.0),
                    "low": _to_float(bar.get("low"), default=0.0),
                    "close": _to_float(bar.get("close"), default=0.0),
                    "volume": _to_float(bar.get("volume"), default=0.0),
                    "quote_volume": _to_float(bar.get("quote_volume"), default=0.0),
                    "trades": int(_to_float(bar.get("trades"), default=0.0)),
                }
            )


class SQLAlchemyRuntimeOMSStateStore:
    """Runtime OMS store backed by core trading tables plus lightweight operational tables."""

    _RUNTIME_EXCHANGE_NAME = "runtime_mock"

    def __init__(self, *, connection: sqlite3.Connection | Engine | Connection, ensure_schema: bool = True) -> None:
        self._db = _StoreConnection(connection=connection)
        if ensure_schema:
            self._ensure_schema()

    def get_order(self, *, order_id: str) -> ReconciliationOrder | None:
        row = self._db.fetchone(
            """
            SELECT
                o.id AS order_id,
                s.symbol AS symbol,
                o.mode AS mode,
                o.quantity AS requested_quantity,
                o.status AS status,
                o.filled_quantity AS filled_quantity,
                o.average_price AS average_price
            FROM orders o
            JOIN symbols s ON s.id = o.symbol_id
            WHERE o.id = :order_id
            """,
            {"order_id": _coerce_uuid(order_id)},
        )
        if row is None:
            return None
        average_price = row.get("average_price")
        return ReconciliationOrder(
            order_id=str(row["order_id"]),
            symbol=str(row["symbol"]),
            mode=str(row["mode"]),
            requested_quantity=Decimal(str(row["requested_quantity"])),
            status=str(row["status"]),
            filled_quantity=Decimal(str(row["filled_quantity"])),
            average_price=Decimal(str(average_price)) if average_price is not None else None,
        )

    def upsert_order(self, order: ReconciliationOrder) -> None:
        exchange_id, symbol_id = self._ensure_symbol_refs(order.symbol)
        now_iso = _utc_now_iso()
        existing = self._db.fetchone(
            """
            SELECT side, type, created_at
            FROM orders
            WHERE id = :order_id
            """,
            {"order_id": _coerce_uuid(order.order_id)},
        )
        side = str(existing["side"]) if existing is not None else "BUY"
        order_type = str(existing["type"]) if existing is not None else "MARKET"
        created_at = str(existing["created_at"]) if existing is not None else now_iso

        self._db.execute(
            """
            INSERT INTO orders
                (id, exchange_id, symbol_id, signal_id, exchange_order_id, client_order_id, side, type, status, mode, price, quantity, filled_quantity, average_price, created_at, updated_at)
            VALUES
                (:id, :exchange_id, :symbol_id, :signal_id, :exchange_order_id, :client_order_id, :side, :type, :status, :mode, :price, :quantity, :filled_quantity, :average_price, :created_at, :updated_at)
            ON CONFLICT (id)
            DO UPDATE SET
                exchange_id = excluded.exchange_id,
                symbol_id = excluded.symbol_id,
                exchange_order_id = excluded.exchange_order_id,
                side = excluded.side,
                type = excluded.type,
                status = excluded.status,
                mode = excluded.mode,
                price = excluded.price,
                quantity = excluded.quantity,
                filled_quantity = excluded.filled_quantity,
                average_price = excluded.average_price,
                updated_at = excluded.updated_at
            """,
            {
                "id": _coerce_uuid(order.order_id),
                "exchange_id": exchange_id,
                "symbol_id": symbol_id,
                "signal_id": None,
                "exchange_order_id": order.order_id,
                "client_order_id": order.order_id,
                "side": side,
                "type": order_type,
                "status": order.status,
                "mode": order.mode,
                "price": float(order.average_price) if order.average_price is not None else None,
                "quantity": float(order.requested_quantity),
                "filled_quantity": float(order.filled_quantity),
                "average_price": float(order.average_price) if order.average_price is not None else None,
                "created_at": created_at,
                "updated_at": now_iso,
            },
        )

    def append_lifecycle_event(self, *, order_id: str, event: LifecycleEvent) -> None:
        fill = event.fill
        now_iso = _utc_now_iso()
        self._db.execute(
            """
            INSERT INTO runtime_oms_lifecycle_events
                (event_id, order_id, event_type, status, fill_id, fill_quantity, fill_price, fill_fee, fill_source, created_at)
            VALUES
                (:event_id, :order_id, :event_type, :status, :fill_id, :fill_quantity, :fill_price, :fill_fee, :fill_source, :created_at)
            """,
            {
                "event_id": str(uuid.uuid4()),
                "order_id": _coerce_uuid(order_id),
                "event_type": event.event_type,
                "status": event.status,
                "fill_id": fill.fill_id if fill is not None else None,
                "fill_quantity": float(fill.quantity) if fill is not None else None,
                "fill_price": float(fill.price) if fill is not None else None,
                "fill_fee": float(fill.fee) if fill is not None else None,
                "fill_source": fill.source if fill is not None else None,
                "created_at": now_iso,
            },
        )

        if fill is None:
            return

        order_row = self._db.fetchone(
            """
            SELECT side, mode
            FROM orders
            WHERE id = :order_id
            """,
            {"order_id": _coerce_uuid(order_id)},
        )
        side = str(order_row["side"]) if order_row is not None else "BUY"
        mode = str(order_row["mode"]) if order_row is not None else "MOCK"
        self._db.execute(
            """
            INSERT INTO fills
                (id, order_id, exchange_fill_id, side, mode, quantity, price, fee, fee_currency, filled_at)
            VALUES
                (:id, :order_id, :exchange_fill_id, :side, :mode, :quantity, :price, :fee, :fee_currency, :filled_at)
            ON CONFLICT (id)
            DO UPDATE SET
                exchange_fill_id = excluded.exchange_fill_id,
                side = excluded.side,
                mode = excluded.mode,
                quantity = excluded.quantity,
                price = excluded.price,
                fee = excluded.fee,
                fee_currency = excluded.fee_currency,
                filled_at = excluded.filled_at
            """,
            {
                "id": _coerce_uuid(fill.fill_id),
                "order_id": _coerce_uuid(order_id),
                "exchange_fill_id": fill.fill_id,
                "side": side,
                "mode": mode,
                "quantity": float(fill.quantity),
                "price": float(fill.price),
                "fee": float(fill.fee),
                "fee_currency": "USD",
                "filled_at": now_iso,
            },
        )

    def load_lifecycle_events(self, *, order_id: str) -> tuple[LifecycleEvent, ...]:
        rows = self._db.fetchall(
            """
            SELECT event_type, status, fill_id, fill_quantity, fill_price, fill_fee, fill_source
            FROM runtime_oms_lifecycle_events
            WHERE order_id = :order_id
            ORDER BY created_at ASC, event_id ASC
            """,
            {"order_id": _coerce_uuid(order_id)},
        )
        events: list[LifecycleEvent] = []
        for row in rows:
            fill: ReconciliationFill | None = None
            fill_id = row.get("fill_id")
            if fill_id is not None:
                fill = ReconciliationFill(
                    fill_id=str(fill_id),
                    order_id=_coerce_uuid(order_id),
                    quantity=Decimal(str(float(row.get("fill_quantity", 0.0) or 0.0))),
                    price=Decimal(str(float(row.get("fill_price", 0.0) or 0.0))),
                    fee=Decimal(str(float(row.get("fill_fee", 0.0) or 0.0))),
                    source=str(row.get("fill_source", "runtime_worker") or "runtime_worker"),
                )
            status_raw = row.get("status")
            status = str(status_raw) if status_raw is not None else None
            events.append(
                LifecycleEvent(
                    event_type=str(row["event_type"]),
                    status=status,
                    fill=fill,
                )
            )
        return tuple(events)

    def get_position(self, *, mode: str, symbol: str) -> PositionState | None:
        row = self._db.fetchone(
            """
            SELECT
                p.mode AS mode,
                s.symbol AS symbol,
                p.quantity AS quantity,
                p.entry_price AS average_entry_price,
                p.realized_pnl AS realized_pnl,
                p.status AS status,
                COALESCE(p.closed_at, p.opened_at) AS updated_at
            FROM positions p
            JOIN symbols s ON s.id = p.symbol_id
            WHERE p.mode = :mode
              AND s.symbol = :symbol
            ORDER BY p.opened_at DESC
            LIMIT 1
            """,
            {"mode": mode, "symbol": symbol},
        )
        if row is None:
            return None
        return PositionState(
            mode=str(row["mode"]),
            symbol=str(row["symbol"]),
            quantity=Decimal(str(row["quantity"])),
            average_entry_price=Decimal(str(row["average_entry_price"])),
            realized_pnl=Decimal(str(row["realized_pnl"])),
            status=str(row["status"]),
            updated_at=str(row["updated_at"]),
        )

    def upsert_position(self, position: PositionState) -> None:
        exchange_id, symbol_id = self._ensure_symbol_refs(position.symbol)
        existing = self._db.fetchone(
            """
            SELECT id, opened_at
            FROM positions
            WHERE mode = :mode
              AND symbol_id = :symbol_id
            ORDER BY opened_at DESC
            LIMIT 1
            """,
            {"mode": position.mode, "symbol_id": symbol_id},
        )
        side = "LONG" if float(position.quantity) > 0 else "SHORT" if float(position.quantity) < 0 else "FLAT"
        closed_at = position.updated_at if position.status.upper() == "CLOSED" else None
        if existing is None:
            self._db.execute(
                """
                INSERT INTO positions
                    (id, exchange_id, symbol_id, mode, side, quantity, entry_price, unrealized_pnl, realized_pnl, status, opened_at, closed_at)
                VALUES
                    (:id, :exchange_id, :symbol_id, :mode, :side, :quantity, :entry_price, :unrealized_pnl, :realized_pnl, :status, :opened_at, :closed_at)
                """,
                {
                    "id": str(uuid.uuid4()),
                    "exchange_id": exchange_id,
                    "symbol_id": symbol_id,
                    "mode": position.mode,
                    "side": side,
                    "quantity": float(position.quantity),
                    "entry_price": float(position.average_entry_price),
                    "unrealized_pnl": 0.0,
                    "realized_pnl": float(position.realized_pnl),
                    "status": position.status,
                    "opened_at": position.updated_at,
                    "closed_at": closed_at,
                },
            )
            return
        self._db.execute(
            """
            UPDATE positions
            SET
                exchange_id = :exchange_id,
                symbol_id = :symbol_id,
                mode = :mode,
                side = :side,
                quantity = :quantity,
                entry_price = :entry_price,
                unrealized_pnl = :unrealized_pnl,
                realized_pnl = :realized_pnl,
                status = :status,
                closed_at = :closed_at
            WHERE id = :id
            """,
            {
                "id": str(existing["id"]),
                "exchange_id": exchange_id,
                "symbol_id": symbol_id,
                "mode": position.mode,
                "side": side,
                "quantity": float(position.quantity),
                "entry_price": float(position.average_entry_price),
                "unrealized_pnl": 0.0,
                "realized_pnl": float(position.realized_pnl),
                "status": position.status,
                "closed_at": closed_at,
            },
        )

    def list_positions(self, *, mode: str) -> tuple[PositionState, ...]:
        rows = self._db.fetchall(
            """
            SELECT
                p.mode AS mode,
                s.symbol AS symbol,
                p.quantity AS quantity,
                p.entry_price AS average_entry_price,
                p.realized_pnl AS realized_pnl,
                p.status AS status,
                COALESCE(p.closed_at, p.opened_at) AS updated_at,
                p.opened_at AS opened_at
            FROM positions p
            JOIN symbols s ON s.id = p.symbol_id
            WHERE p.mode = :mode
            ORDER BY s.symbol ASC, p.opened_at DESC
            """,
            {"mode": mode},
        )
        deduped: dict[str, PositionState] = {}
        for row in rows:
            symbol = str(row["symbol"])
            if symbol in deduped:
                continue
            deduped[symbol] = PositionState(
                mode=str(row["mode"]),
                symbol=symbol,
                quantity=Decimal(str(row["quantity"])),
                average_entry_price=Decimal(str(row["average_entry_price"])),
                realized_pnl=Decimal(str(row["realized_pnl"])),
                status=str(row["status"]),
                updated_at=str(row["updated_at"]),
            )
        return tuple(deduped[key] for key in sorted(deduped))

    def upsert_mark_price(self, *, mode: str, symbol: str, mark_price: float | Decimal) -> None:
        self._db.execute(
            """
            INSERT INTO runtime_oms_mark_prices
                (mode, symbol, mark_price, updated_at)
            VALUES
                (:mode, :symbol, :mark_price, :updated_at)
            ON CONFLICT (mode, symbol)
            DO UPDATE SET
                mark_price = excluded.mark_price,
                updated_at = excluded.updated_at
            """,
            {
                "mode": mode,
                "symbol": symbol,
                "mark_price": float(mark_price),
                "updated_at": _utc_now_iso(),
            },
        )

    def load_mark_prices(self, *, mode: str) -> dict[str, float]:
        rows = self._db.fetchall(
            """
            SELECT symbol, mark_price
            FROM runtime_oms_mark_prices
            WHERE mode = :mode
            """,
            {"mode": mode},
        )
        return {str(row["symbol"]): float(row["mark_price"]) for row in rows}

    def insert_portfolio_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        self._db.execute(
            """
            INSERT INTO portfolio_snapshots
                (snapshot_time, mode, total_balance_usd, available_balance_usd, locked_balance_usd, unrealized_pnl, realized_pnl_total, created_at)
            VALUES
                (:snapshot_time, :mode, :total_balance_usd, :available_balance_usd, :locked_balance_usd, :unrealized_pnl, :realized_pnl_total, :created_at)
            """,
            {
                "snapshot_time": snapshot.snapshot_time,
                "mode": snapshot.mode,
                "total_balance_usd": float(snapshot.total_balance_usd),
                "available_balance_usd": float(snapshot.available_balance_usd),
                "locked_balance_usd": float(snapshot.locked_balance_usd),
                "unrealized_pnl": float(snapshot.unrealized_pnl),
                "realized_pnl_total": float(snapshot.realized_pnl_total),
                "created_at": _utc_now_iso(),
            },
        )

    def _runtime_exchange_id(self) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, self._RUNTIME_EXCHANGE_NAME))

    def _ensure_symbol_refs(self, symbol: str) -> tuple[str, str]:
        normalized_symbol = symbol.strip().upper()
        exchange_id = self._runtime_exchange_id()
        now_iso = _utc_now_iso()
        self._db.execute(
            """
            INSERT INTO exchanges
                (id, name, api_key_encrypted, api_secret_encrypted, is_active, created_at)
            VALUES
                (:id, :name, :api_key_encrypted, :api_secret_encrypted, :is_active, :created_at)
            ON CONFLICT (name)
            DO NOTHING
            """,
            {
                "id": exchange_id,
                "name": self._RUNTIME_EXCHANGE_NAME,
                "api_key_encrypted": None,
                "api_secret_encrypted": None,
                "is_active": True,
                "created_at": now_iso,
            },
        )
        existing_symbol = self._db.fetchone(
            """
            SELECT id
            FROM symbols
            WHERE exchange_id = :exchange_id
              AND symbol = :symbol
            """,
            {"exchange_id": exchange_id, "symbol": normalized_symbol},
        )
        if existing_symbol is not None:
            return exchange_id, str(existing_symbol["id"])
        base_asset, quote_asset = _split_symbol(normalized_symbol)
        symbol_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{exchange_id}:{normalized_symbol}"))
        self._db.execute(
            """
            INSERT INTO symbols
                (id, exchange_id, symbol, base_asset, quote_asset, is_active, created_at)
            VALUES
                (:id, :exchange_id, :symbol, :base_asset, :quote_asset, :is_active, :created_at)
            ON CONFLICT (exchange_id, symbol)
            DO NOTHING
            """,
            {
                "id": symbol_id,
                "exchange_id": exchange_id,
                "symbol": normalized_symbol,
                "base_asset": base_asset,
                "quote_asset": quote_asset,
                "is_active": True,
                "created_at": now_iso,
            },
        )
        return exchange_id, symbol_id

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS exchanges (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                api_key_encrypted TEXT NULL,
                api_secret_encrypted TEXT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """,
            {},
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS symbols (
                id TEXT PRIMARY KEY,
                exchange_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                base_asset TEXT NOT NULL,
                quote_asset TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                UNIQUE(exchange_id, symbol)
            )
            """,
            {},
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                exchange_id TEXT NOT NULL,
                symbol_id TEXT NOT NULL,
                signal_id TEXT NULL,
                exchange_order_id TEXT NULL,
                client_order_id TEXT NOT NULL,
                side TEXT NOT NULL,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                mode TEXT NOT NULL,
                price REAL NULL,
                quantity REAL NOT NULL,
                filled_quantity REAL NOT NULL,
                average_price REAL NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            {},
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS fills (
                id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                exchange_fill_id TEXT NOT NULL,
                side TEXT NOT NULL,
                mode TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                fee REAL NOT NULL,
                fee_currency TEXT NULL,
                filled_at TEXT NOT NULL
            )
            """,
            {},
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS positions (
                id TEXT PRIMARY KEY,
                exchange_id TEXT NOT NULL,
                symbol_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                entry_price REAL NOT NULL,
                unrealized_pnl REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                status TEXT NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT NULL
            )
            """,
            {},
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY,
                snapshot_time TEXT NOT NULL,
                mode TEXT NOT NULL,
                total_balance_usd REAL NOT NULL,
                available_balance_usd REAL NOT NULL,
                locked_balance_usd REAL NOT NULL,
                unrealized_pnl REAL NOT NULL,
                realized_pnl_total REAL NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            {},
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_oms_lifecycle_events (
                event_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                status TEXT NULL,
                fill_id TEXT NULL,
                fill_quantity REAL NULL,
                fill_price REAL NULL,
                fill_fee REAL NULL,
                fill_source TEXT NULL,
                created_at TEXT NOT NULL
            )
            """,
            {},
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_oms_mark_prices (
                mode TEXT NOT NULL,
                symbol TEXT NOT NULL,
                mark_price REAL NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (mode, symbol)
            )
            """,
            {},
        )


class SQLAlchemyNewsItemStore:
    """News item dedupe store backed by sqlite or SQLAlchemy."""

    def __init__(self, *, connection: sqlite3.Connection | Engine | Connection, ensure_schema: bool = True) -> None:
        self._db = _StoreConnection(connection=connection)
        if ensure_schema:
            self._ensure_schema()

    def has_source_item(self, *, source: str, source_item_id: str) -> bool:
        row = self._db.fetchone(
            """
            SELECT 1
            FROM news_items
            WHERE source = :source AND source_item_id = :source_item_id
            """,
            {"source": source, "source_item_id": source_item_id},
        )
        return row is not None

    def has_hash(self, *, content_hash: str) -> bool:
        row = self._db.fetchone(
            """
            SELECT 1
            FROM news_items
            WHERE hash = :content_hash
            """,
            {"content_hash": content_hash},
        )
        return row is not None

    def persist_item(self, item: NormalizedNewsItem) -> None:
        self._db.execute(
            """
            INSERT INTO news_items
                (news_id, source, source_item_id, url, title, body, published_at, ingested_at, hash, language, raw_payload)
            VALUES
                (:news_id, :source, :source_item_id, :url, :title, :body, :published_at, :ingested_at, :hash, :language, :raw_payload)
            ON CONFLICT (source, source_item_id)
            DO UPDATE SET
                url = excluded.url,
                title = excluded.title,
                body = excluded.body,
                published_at = excluded.published_at,
                ingested_at = excluded.ingested_at,
                hash = excluded.hash,
                language = excluded.language,
                raw_payload = excluded.raw_payload
            """,
            {
                "news_id": item.news_id,
                "source": item.source,
                "source_item_id": item.source_item_id,
                "url": item.url,
                "title": item.title,
                "body": item.body,
                "published_at": item.published_at,
                "ingested_at": item.ingested_at,
                "hash": item.content_hash,
                "language": item.language,
                "raw_payload": json.dumps(item.raw_payload, ensure_ascii=True),
            },
        )

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS news_items (
                news_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                source_item_id TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NULL,
                published_at TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                hash TEXT NOT NULL,
                language TEXT NOT NULL,
                raw_payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            {},
        )
        self._db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_news_items_source_source_item_id
            ON news_items (source, source_item_id)
            """,
            {},
        )
        self._db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_news_items_hash
            ON news_items (hash)
            """,
            {},
        )


class SQLAlchemyNewsTagStore:
    def __init__(self, *, connection: sqlite3.Connection | Engine | Connection, ensure_schema: bool = True) -> None:
        self._db = _StoreConnection(connection=connection)
        if ensure_schema:
            self._ensure_schema()

    def persist_tag(self, tag: NewsTag) -> None:
        self._db.execute(
            """
            INSERT INTO news_tags
                (news_id, symbol, topic, relevance_score, sentiment_score, created_at)
            VALUES
                (:news_id, :symbol, :topic, :relevance_score, :sentiment_score, :created_at)
            """,
            {
                "news_id": tag.news_id,
                "symbol": tag.symbol,
                "topic": tag.topic,
                "relevance_score": float(tag.relevance_score),
                "sentiment_score": float(tag.sentiment_score),
                "created_at": _utc_now_iso(),
            },
        )

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS news_tags (
                id INTEGER PRIMARY KEY,
                news_id TEXT NOT NULL,
                symbol TEXT NULL,
                topic TEXT NULL,
                relevance_score REAL NOT NULL,
                sentiment_score REAL NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            {},
        )


class SQLAlchemyNewsSummaryStore:
    def __init__(self, *, connection: sqlite3.Connection | Engine | Connection, ensure_schema: bool = True) -> None:
        self._db = _StoreConnection(connection=connection)
        if ensure_schema:
            self._ensure_schema()

    def persist_summary(self, summary: NewsSummaryArtifact) -> None:
        self._db.execute(
            """
            INSERT INTO news_summaries
                (summary_id, symbol_scope, window_start, window_end, summary_text, token_count, generated_at)
            VALUES
                (:summary_id, :symbol_scope, :window_start, :window_end, :summary_text, :token_count, :generated_at)
            ON CONFLICT (symbol_scope, window_start, window_end)
            DO UPDATE SET
                summary_id = excluded.summary_id,
                summary_text = excluded.summary_text,
                token_count = excluded.token_count,
                generated_at = excluded.generated_at
            """,
            {
                "summary_id": summary.summary_id,
                "symbol_scope": summary.symbol_scope,
                "window_start": summary.window_start,
                "window_end": summary.window_end,
                "summary_text": summary.summary_text,
                "token_count": int(summary.token_count),
                "generated_at": summary.generated_at,
            },
        )
        for news_id in summary.source_news_ids:
            self._db.execute(
                """
                INSERT INTO news_summary_sources
                    (summary_id, news_id, created_at)
                VALUES
                    (:summary_id, :news_id, :created_at)
                ON CONFLICT (summary_id, news_id)
                DO NOTHING
                """,
                {
                    "summary_id": summary.summary_id,
                    "news_id": news_id,
                    "created_at": _utc_now_iso(),
                },
            )

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS news_summaries (
                summary_id TEXT PRIMARY KEY,
                symbol_scope TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                summary_text TEXT NOT NULL,
                token_count INTEGER NOT NULL,
                generated_at TEXT NOT NULL
            )
            """,
            {},
        )
        self._db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_news_summaries_scope_window
            ON news_summaries (symbol_scope, window_start, window_end)
            """,
            {},
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS news_summary_sources (
                summary_id TEXT NOT NULL,
                news_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (summary_id, news_id)
            )
            """,
            {},
        )


class _StoreConnection:
    def __init__(self, *, connection: sqlite3.Connection | Engine | Connection) -> None:
        self._sqlite_connection: sqlite3.Connection | None = None
        self._engine: Engine | None = None
        if isinstance(connection, sqlite3.Connection):
            self._sqlite_connection = connection
            self._sqlite_connection.row_factory = sqlite3.Row
            return
        if isinstance(connection, Engine):
            self._engine = connection
            return
        if isinstance(connection, Connection):
            self._engine = connection.engine
            return
        raise TypeError("connection must be sqlite3.Connection, sqlalchemy.Engine, or sqlalchemy.Connection")

    def execute(self, statement: str, params: Mapping[str, Any]) -> None:
        if self._sqlite_connection is not None:
            self._sqlite_connection.execute(statement, dict(params))
            self._sqlite_connection.commit()
            return
        if self._engine is None:
            raise RuntimeError("store connection was not initialized with a valid bind")
        with self._engine.begin() as connection:
            connection.execute(text(statement), dict(params))

    def fetchone(self, statement: str, params: Mapping[str, Any]) -> dict[str, Any] | None:
        if self._sqlite_connection is not None:
            row = self._sqlite_connection.execute(statement, dict(params)).fetchone()
            if row is None:
                return None
            return dict(row)
        if self._engine is None:
            raise RuntimeError("store connection was not initialized with a valid bind")
        with self._engine.connect() as connection:
            row = connection.execute(text(statement), dict(params)).mappings().first()
            if row is None:
                return None
            return dict(row)

    def fetchall(self, statement: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
        if self._sqlite_connection is not None:
            rows = self._sqlite_connection.execute(statement, dict(params)).fetchall()
            return [dict(row) for row in rows]
        if self._engine is None:
            raise RuntimeError("store connection was not initialized with a valid bind")
        with self._engine.connect() as connection:
            rows = connection.execute(text(statement), dict(params)).mappings().all()
            return [dict(row) for row in rows]


def _coerce_uuid(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(normalized))
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, normalized))


def _split_symbol(symbol: str) -> tuple[str, str]:
    normalized = symbol.strip().upper()
    if "/" not in normalized:
        return normalized or "UNKNOWN", "USD"
    base, quote = normalized.split("/", 1)
    base_asset = base.strip() or "UNKNOWN"
    quote_asset = quote.strip() or "USD"
    return base_asset, quote_asset


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _as_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value
    try:
        timestamp_ms = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_levels(value: Any) -> list[dict[str, float]]:
    if not isinstance(value, list):
        return []
    levels: list[dict[str, float]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        price = _to_float(raw.get("price"), default=0.0)
        amount = _to_float(raw.get("amount"), default=0.0)
        if price <= 0.0 or amount <= 0.0:
            continue
        levels.append({"price": price, "amount": amount})
    return levels


def _compute_spread_bps(*, best_bid: float, best_ask: float) -> float:
    if best_bid <= 0.0 or best_ask <= 0.0:
        return 0.0
    mid = (best_bid + best_ask) / 2.0
    if mid <= 0.0:
        return 0.0
    return ((best_ask - best_bid) / mid) * 10_000.0


def _to_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
