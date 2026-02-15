from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
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


class SQLAlchemyRuntimeOMSStateStore:
    """Runtime OMS state store backed by sqlite or SQLAlchemy."""

    def __init__(self, *, connection: sqlite3.Connection | Engine | Connection, ensure_schema: bool = True) -> None:
        self._db = _StoreConnection(connection=connection)
        if ensure_schema:
            self._ensure_schema()

    def get_order(self, *, order_id: str) -> ReconciliationOrder | None:
        row = self._db.fetchone(
            """
            SELECT order_id, symbol, mode, requested_quantity, status, filled_quantity, average_price
            FROM runtime_oms_orders
            WHERE order_id = :order_id
            """,
            {"order_id": order_id},
        )
        if row is None:
            return None
        average_price = row.get("average_price")
        return ReconciliationOrder(
            order_id=str(row["order_id"]),
            symbol=str(row["symbol"]),
            mode=str(row["mode"]),
            requested_quantity=float(row["requested_quantity"]),
            status=str(row["status"]),
            filled_quantity=float(row["filled_quantity"]),
            average_price=float(average_price) if average_price is not None else None,
        )

    def upsert_order(self, order: ReconciliationOrder) -> None:
        self._db.execute(
            """
            INSERT INTO runtime_oms_orders
                (order_id, symbol, mode, requested_quantity, status, filled_quantity, average_price, updated_at)
            VALUES
                (:order_id, :symbol, :mode, :requested_quantity, :status, :filled_quantity, :average_price, :updated_at)
            ON CONFLICT (order_id)
            DO UPDATE SET
                symbol = excluded.symbol,
                mode = excluded.mode,
                requested_quantity = excluded.requested_quantity,
                status = excluded.status,
                filled_quantity = excluded.filled_quantity,
                average_price = excluded.average_price,
                updated_at = excluded.updated_at
            """,
            {
                "order_id": order.order_id,
                "symbol": order.symbol,
                "mode": order.mode,
                "requested_quantity": float(order.requested_quantity),
                "status": order.status,
                "filled_quantity": float(order.filled_quantity),
                "average_price": float(order.average_price) if order.average_price is not None else None,
                "updated_at": _utc_now_iso(),
            },
        )

    def append_lifecycle_event(self, *, order_id: str, event: LifecycleEvent) -> None:
        fill = event.fill
        self._db.execute(
            """
            INSERT INTO runtime_oms_lifecycle_events
                (event_id, order_id, event_type, status, fill_id, fill_quantity, fill_price, fill_fee, fill_source, created_at)
            VALUES
                (:event_id, :order_id, :event_type, :status, :fill_id, :fill_quantity, :fill_price, :fill_fee, :fill_source, :created_at)
            """,
            {
                "event_id": str(uuid.uuid4()),
                "order_id": order_id,
                "event_type": event.event_type,
                "status": event.status,
                "fill_id": fill.fill_id if fill is not None else None,
                "fill_quantity": float(fill.quantity) if fill is not None else None,
                "fill_price": float(fill.price) if fill is not None else None,
                "fill_fee": float(fill.fee) if fill is not None else None,
                "fill_source": fill.source if fill is not None else None,
                "created_at": _utc_now_iso(),
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
            {"order_id": order_id},
        )
        events: list[LifecycleEvent] = []
        for row in rows:
            fill: ReconciliationFill | None = None
            fill_id = row.get("fill_id")
            if fill_id is not None:
                fill = ReconciliationFill(
                    fill_id=str(fill_id),
                    order_id=order_id,
                    quantity=float(row.get("fill_quantity", 0.0) or 0.0),
                    price=float(row.get("fill_price", 0.0) or 0.0),
                    fee=float(row.get("fill_fee", 0.0) or 0.0),
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
            SELECT mode, symbol, quantity, average_entry_price, realized_pnl, status, updated_at
            FROM runtime_oms_positions
            WHERE mode = :mode AND symbol = :symbol
            """,
            {"mode": mode, "symbol": symbol},
        )
        if row is None:
            return None
        return PositionState(
            mode=str(row["mode"]),
            symbol=str(row["symbol"]),
            quantity=float(row["quantity"]),
            average_entry_price=float(row["average_entry_price"]),
            realized_pnl=float(row["realized_pnl"]),
            status=str(row["status"]),
            updated_at=str(row["updated_at"]),
        )

    def upsert_position(self, position: PositionState) -> None:
        self._db.execute(
            """
            INSERT INTO runtime_oms_positions
                (mode, symbol, quantity, average_entry_price, realized_pnl, status, updated_at)
            VALUES
                (:mode, :symbol, :quantity, :average_entry_price, :realized_pnl, :status, :updated_at)
            ON CONFLICT (mode, symbol)
            DO UPDATE SET
                quantity = excluded.quantity,
                average_entry_price = excluded.average_entry_price,
                realized_pnl = excluded.realized_pnl,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            {
                "mode": position.mode,
                "symbol": position.symbol,
                "quantity": float(position.quantity),
                "average_entry_price": float(position.average_entry_price),
                "realized_pnl": float(position.realized_pnl),
                "status": position.status,
                "updated_at": position.updated_at,
            },
        )

    def list_positions(self, *, mode: str) -> tuple[PositionState, ...]:
        rows = self._db.fetchall(
            """
            SELECT mode, symbol, quantity, average_entry_price, realized_pnl, status, updated_at
            FROM runtime_oms_positions
            WHERE mode = :mode
            ORDER BY symbol ASC
            """,
            {"mode": mode},
        )
        return tuple(
            PositionState(
                mode=str(row["mode"]),
                symbol=str(row["symbol"]),
                quantity=float(row["quantity"]),
                average_entry_price=float(row["average_entry_price"]),
                realized_pnl=float(row["realized_pnl"]),
                status=str(row["status"]),
                updated_at=str(row["updated_at"]),
            )
            for row in rows
        )

    def upsert_mark_price(self, *, mode: str, symbol: str, mark_price: float) -> None:
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
        next_snapshot_id = self._next_portfolio_snapshot_id()
        self._db.execute(
            """
            INSERT INTO runtime_oms_portfolio_snapshots
                (id, snapshot_time, mode, total_balance_usd, available_balance_usd, locked_balance_usd, unrealized_pnl, realized_pnl_today, created_at)
            VALUES
                (:id, :snapshot_time, :mode, :total_balance_usd, :available_balance_usd, :locked_balance_usd, :unrealized_pnl, :realized_pnl_today, :created_at)
            """,
            {
                "id": next_snapshot_id,
                "snapshot_time": snapshot.snapshot_time,
                "mode": snapshot.mode,
                "total_balance_usd": float(snapshot.total_balance_usd),
                "available_balance_usd": float(snapshot.available_balance_usd),
                "locked_balance_usd": float(snapshot.locked_balance_usd),
                "unrealized_pnl": float(snapshot.unrealized_pnl),
                "realized_pnl_today": float(snapshot.realized_pnl_today),
                "created_at": _utc_now_iso(),
            },
        )

    def _next_portfolio_snapshot_id(self) -> int:
        row = self._db.fetchone(
            """
            SELECT COALESCE(MAX(id), 0) AS max_id
            FROM runtime_oms_portfolio_snapshots
            """,
            {},
        )
        current = int(row["max_id"]) if row is not None and row.get("max_id") is not None else 0
        return current + 1

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_oms_orders (
                order_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                mode TEXT NOT NULL,
                requested_quantity REAL NOT NULL,
                status TEXT NOT NULL,
                filled_quantity REAL NOT NULL,
                average_price REAL NULL,
                updated_at TEXT NOT NULL
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
            CREATE TABLE IF NOT EXISTS runtime_oms_positions (
                mode TEXT NOT NULL,
                symbol TEXT NOT NULL,
                quantity REAL NOT NULL,
                average_entry_price REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (mode, symbol)
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
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_oms_portfolio_snapshots (
                id INTEGER PRIMARY KEY,
                snapshot_time TEXT NOT NULL,
                mode TEXT NOT NULL,
                total_balance_usd REAL NOT NULL,
                available_balance_usd REAL NOT NULL,
                locked_balance_usd REAL NOT NULL,
                unrealized_pnl REAL NOT NULL,
                realized_pnl_today REAL NOT NULL,
                created_at TEXT NOT NULL
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
                INSERT INTO runtime_news_summary_sources
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
            CREATE TABLE IF NOT EXISTS runtime_news_summary_sources (
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
