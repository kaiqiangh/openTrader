from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Mapping
import json
import sqlite3

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from services.agent_orchestrator.memory_layer import DecisionMemoryRecord


class InMemoryTTLShortTermStore:
    """Concrete short-term memory store with TTL semantics."""

    def __init__(self, *, clock=monotonic) -> None:
        self._clock = clock
        self._slots: dict[tuple[str, str, str, str], tuple[dict[str, Any], float]] = {}

    async def write_slot(
        self,
        *,
        mode: str,
        strategy_id: str,
        decision_id: str,
        slot: str,
        payload: Mapping[str, Any],
        ttl_seconds: int,
    ) -> None:
        expires_at = self._clock() + max(int(ttl_seconds), 1)
        key = (mode, strategy_id, decision_id, slot)
        self._slots[key] = (dict(payload), expires_at)

    async def read_slots(
        self,
        *,
        mode: str,
        strategy_id: str,
        decision_id: str,
    ) -> Mapping[str, Mapping[str, Any]]:
        now = self._clock()
        scoped: dict[str, dict[str, Any]] = {}
        expired: list[tuple[str, str, str, str]] = []
        for key, (payload, expires_at) in self._slots.items():
            key_mode, key_strategy, key_decision, slot = key
            if expires_at <= now:
                expired.append(key)
                continue
            if key_mode == mode and key_strategy == strategy_id and key_decision == decision_id:
                scoped[slot] = dict(payload)

        for key in expired:
            self._slots.pop(key, None)
        return scoped


class SQLiteShortTermMemoryStore:
    """Concrete short-term memory store backed by sqlite or SQLAlchemy engine."""

    def __init__(self, *, connection: sqlite3.Connection | Engine | Connection) -> None:
        self._sqlite_connection: sqlite3.Connection | None = None
        self._engine: Engine | None = None
        if isinstance(connection, sqlite3.Connection):
            self._sqlite_connection = connection
            self._sqlite_connection.row_factory = sqlite3.Row
        elif isinstance(connection, Engine):
            self._engine = connection
        elif isinstance(connection, Connection):
            self._engine = connection.engine
        else:
            raise TypeError("connection must be sqlite3.Connection, sqlalchemy.Engine, or sqlalchemy.Connection")
        self._ensure_schema()

    async def write_slot(
        self,
        *,
        mode: str,
        strategy_id: str,
        decision_id: str,
        slot: str,
        payload: Mapping[str, Any],
        ttl_seconds: int,
    ) -> None:
        expires_at = _utc_future_iso(max(int(ttl_seconds), 1))
        self._execute(
            """
            INSERT INTO runtime_decision_slots
                (mode, strategy_id, decision_id, slot, payload_json, expires_at, updated_at)
            VALUES
                (:mode, :strategy_id, :decision_id, :slot, :payload_json, :expires_at, :updated_at)
            ON CONFLICT (mode, strategy_id, decision_id, slot)
            DO UPDATE SET
                payload_json = excluded.payload_json,
                expires_at = excluded.expires_at,
                updated_at = excluded.updated_at
            """,
            {
                "mode": mode,
                "strategy_id": strategy_id,
                "decision_id": decision_id,
                "slot": slot,
                "payload_json": json.dumps(dict(payload), ensure_ascii=True),
                "expires_at": expires_at,
                "updated_at": utc_now_iso(),
            },
        )

    async def read_slots(
        self,
        *,
        mode: str,
        strategy_id: str,
        decision_id: str,
    ) -> Mapping[str, Mapping[str, Any]]:
        now_iso = utc_now_iso()
        self._execute(
            """
            DELETE FROM runtime_decision_slots
            WHERE expires_at <= :now_iso
            """,
            {"now_iso": now_iso},
        )
        rows = self._fetch_all(
            """
            SELECT slot, payload_json
            FROM runtime_decision_slots
            WHERE mode = :mode
              AND strategy_id = :strategy_id
              AND decision_id = :decision_id
              AND expires_at > :now_iso
            """,
            {
                "mode": mode,
                "strategy_id": strategy_id,
                "decision_id": decision_id,
                "now_iso": now_iso,
            },
        )
        slots: dict[str, Mapping[str, Any]] = {}
        for row in rows:
            parsed_payload = json.loads(str(row["payload_json"]))
            slots[str(row["slot"])] = _ensure_mapping(parsed_payload)
        return slots

    def _ensure_schema(self) -> None:
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_decision_slots (
                mode TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                decision_id TEXT NOT NULL,
                slot TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (mode, strategy_id, decision_id, slot)
            )
            """,
            {},
        )
        self._execute(
            """
            CREATE INDEX IF NOT EXISTS idx_runtime_decision_slots_expiry
            ON runtime_decision_slots (expires_at)
            """,
            {},
        )

    def _execute(self, statement: str, params: Mapping[str, Any]) -> None:
        if self._sqlite_connection is not None:
            self._sqlite_connection.execute(statement, params)
            self._sqlite_connection.commit()
            return
        if self._engine is None:
            raise RuntimeError("short-term memory store was not initialized with a valid connection")
        with self._engine.begin() as connection:
            connection.execute(text(statement), dict(params))

    def _fetch_all(self, statement: str, params: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        if self._sqlite_connection is not None:
            rows = self._sqlite_connection.execute(statement, params).fetchall()
            return [dict(row) for row in rows]
        if self._engine is None:
            raise RuntimeError("short-term memory store was not initialized with a valid connection")
        with self._engine.connect() as connection:
            rows = connection.execute(text(statement), dict(params)).mappings().all()
            return [dict(row) for row in rows]


class SQLiteLongTermMemoryStore:
    """Concrete long-term memory store backed by sqlite or SQLAlchemy engine."""

    def __init__(self, *, connection: sqlite3.Connection | Engine | Connection) -> None:
        self._sqlite_connection: sqlite3.Connection | None = None
        self._engine: Engine | None = None
        if isinstance(connection, sqlite3.Connection):
            self._sqlite_connection = connection
            self._sqlite_connection.row_factory = sqlite3.Row
        elif isinstance(connection, Engine):
            self._engine = connection
        elif isinstance(connection, Connection):
            self._engine = connection.engine
        else:
            raise TypeError("connection must be sqlite3.Connection, sqlalchemy.Engine, or sqlalchemy.Connection")
        self._ensure_schema()

    async def persist_decision_summary(self, record: DecisionMemoryRecord) -> None:
        self._execute(
            """
            INSERT INTO runtime_decision_memory
                (decision_id, trace_id, strategy_id, mode, status, summary_json, lifecycle_json, persisted_at)
            VALUES
                (:decision_id, :trace_id, :strategy_id, :mode, :status, :summary_json, :lifecycle_json, :persisted_at)
            ON CONFLICT (decision_id)
            DO UPDATE SET
                trace_id = excluded.trace_id,
                strategy_id = excluded.strategy_id,
                mode = excluded.mode,
                status = excluded.status,
                summary_json = excluded.summary_json,
                lifecycle_json = excluded.lifecycle_json,
                persisted_at = excluded.persisted_at
            """,
            {
                "decision_id": record.decision_id,
                "trace_id": record.trace_id,
                "strategy_id": record.strategy_id,
                "mode": record.mode,
                "status": record.status,
                "summary_json": json.dumps(record.summary, ensure_ascii=True),
                "lifecycle_json": json.dumps([dict(item) for item in record.lifecycle], ensure_ascii=True),
                "persisted_at": record.persisted_at,
            },
        )

    async def read_decision_summary(self, *, decision_id: str) -> DecisionMemoryRecord | None:
        row = self._fetch_one(
            """
            SELECT
                decision_id,
                trace_id,
                strategy_id,
                mode,
                status,
                summary_json,
                lifecycle_json,
                persisted_at
            FROM runtime_decision_memory
            WHERE decision_id = :decision_id
            """,
            {"decision_id": decision_id},
        ).fetchone()
        if row is None:
            return None

        summary_payload = json.loads(str(row["summary_json"]))
        lifecycle_payload = json.loads(str(row["lifecycle_json"]))
        return DecisionMemoryRecord(
            trace_id=str(row["trace_id"]),
            decision_id=str(row["decision_id"]),
            strategy_id=str(row["strategy_id"]),
            mode=str(row["mode"]),
            status=str(row["status"]),
            summary=_ensure_mapping(summary_payload),
            lifecycle=tuple(_ensure_mapping(item) for item in lifecycle_payload),
            persisted_at=str(row["persisted_at"]),
        )

    def _ensure_schema(self) -> None:
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_decision_memory (
                decision_id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                lifecycle_json TEXT NOT NULL,
                persisted_at TEXT NOT NULL
            )
            """,
            {},
        )

    def _execute(self, statement: str, params: Mapping[str, Any]) -> None:
        if self._sqlite_connection is not None:
            self._sqlite_connection.execute(statement, params)
            self._sqlite_connection.commit()
            return
        if self._engine is None:
            raise RuntimeError("long-term memory store was not initialized with a valid connection")
        with self._engine.begin() as connection:
            connection.execute(text(statement), dict(params))

    def _fetch_one(self, statement: str, params: Mapping[str, Any]):
        if self._sqlite_connection is not None:
            return self._sqlite_connection.execute(statement, params)
        if self._engine is None:
            raise RuntimeError("long-term memory store was not initialized with a valid connection")
        with self._engine.connect() as connection:
            return _RowProxy(connection.execute(text(statement), dict(params)).mappings().first())


class _RowProxy:
    def __init__(self, row: Mapping[str, Any] | None) -> None:
        self._row = dict(row) if row is not None else None

    def fetchone(self):
        return self._row


# Backward-compatible alias for previous contract naming.
SQLAlchemyShortTermMemoryStore = SQLiteShortTermMemoryStore
SQLAlchemyLongTermMemoryStore = SQLiteLongTermMemoryStore


def _ensure_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): _ensure_payload(item) for key, item in value.items()}
    return {"value": _ensure_payload(value)}


def _ensure_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _ensure_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_ensure_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_ensure_payload(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return _ensure_payload(asdict(value))
    return value


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc_future_iso(ttl_seconds: int) -> str:
    return datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() + max(ttl_seconds, 1),
        tz=timezone.utc,
    ).isoformat().replace("+00:00", "Z")
