from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Mapping
import json
import sqlite3

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


class SQLiteLongTermMemoryStore:
    """Concrete long-term memory store backed by sqlite3."""

    def __init__(self, *, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        self._ensure_schema()

    async def persist_decision_summary(self, record: DecisionMemoryRecord) -> None:
        self.connection.execute(
            """
            INSERT INTO runtime_decision_memory
                (decision_id, trace_id, strategy_id, mode, status, summary_json, lifecycle_json, persisted_at)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?)
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
            (
                record.decision_id,
                record.trace_id,
                record.strategy_id,
                record.mode,
                record.status,
                json.dumps(record.summary, ensure_ascii=True),
                json.dumps([dict(item) for item in record.lifecycle], ensure_ascii=True),
                record.persisted_at,
            ),
        )
        self.connection.commit()

    async def read_decision_summary(self, *, decision_id: str) -> DecisionMemoryRecord | None:
        row = self.connection.execute(
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
            WHERE decision_id = ?
            """,
            (decision_id,),
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
        self.connection.execute(
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
            """
        )
        self.connection.commit()


# Backward-compatible alias for previous contract naming.
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
