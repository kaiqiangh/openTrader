from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import json
import sqlite3
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from services.agent_orchestrator.replay_service import (
    AgentMessageRecord,
    AgentRunRecord,
    DecisionTraceRecord,
)
from services.llm_gateway.persistence import LLMCallRecord


@dataclass(frozen=True, slots=True)
class TraceAgentRun:
    agent_name: str
    status: str
    latency_ms: float | None
    started_at: str
    completed_at: str | None
    input_payload: Mapping[str, Any]
    output_payload: Mapping[str, Any]


class SQLAlchemyTraceStore:
    def __init__(
        self, *, connection: sqlite3.Connection | Engine | Connection, ensure_schema: bool = True
    ) -> None:
        self._db = _StoreConnection(connection=connection)
        if ensure_schema:
            self._ensure_schema()

    async def persist_cycle(
        self,
        *,
        trace_id: str,
        decision_id: str,
        strategy_id: str,
        mode: str,
        status: str,
        started_at: str,
        completed_at: str | None,
        runs: Sequence[TraceAgentRun],
        decision_news_links: Sequence[tuple[str, str]],
    ) -> None:
        normalized_decision_id = _coerce_uuid(decision_id)
        normalized_strategy_id = _coerce_uuid(strategy_id)
        normalized_mode = mode.strip().upper() or "MOCK"
        normalized_trace_id = trace_id.strip() or normalized_decision_id
        created_at = _utc_now_iso()

        self._db.execute(
            """
            INSERT INTO decision_traces
                (decision_id, trace_id, strategy_id, mode, status, started_at, completed_at, created_at)
            VALUES
                (:decision_id, :trace_id, :strategy_id, :mode, :status, :started_at, :completed_at, :created_at)
            ON CONFLICT (decision_id)
            DO UPDATE SET
                trace_id = excluded.trace_id,
                strategy_id = excluded.strategy_id,
                mode = excluded.mode,
                status = excluded.status,
                started_at = excluded.started_at,
                completed_at = excluded.completed_at
            """,
            {
                "decision_id": normalized_decision_id,
                "trace_id": normalized_trace_id,
                "strategy_id": normalized_strategy_id,
                "mode": normalized_mode,
                "status": status,
                "started_at": started_at,
                "completed_at": completed_at,
                "created_at": created_at,
            },
        )

        for run in runs:
            run_id = str(uuid.uuid4())
            self._db.execute(
                """
                INSERT INTO agent_runs
                    (agent_run_id, decision_id, agent_name, input_ref, output_ref, latency_ms, status, started_at, completed_at, created_at)
                VALUES
                    (:agent_run_id, :decision_id, :agent_name, :input_ref, :output_ref, :latency_ms, :status, :started_at, :completed_at, :created_at)
                ON CONFLICT (agent_run_id)
                DO NOTHING
                """,
                {
                    "agent_run_id": run_id,
                    "decision_id": normalized_decision_id,
                    "agent_name": run.agent_name,
                    "input_ref": f"agent_message:{run_id}:input",
                    "output_ref": f"agent_message:{run_id}:output",
                    "latency_ms": float(run.latency_ms) if run.latency_ms is not None else None,
                    "status": run.status,
                    "started_at": run.started_at,
                    "completed_at": run.completed_at,
                    "created_at": created_at,
                },
            )
            self._persist_agent_message(
                agent_run_id=run_id,
                role="input",
                payload_json=run.input_payload,
                created_at=run.started_at,
            )
            self._persist_agent_message(
                agent_run_id=run_id,
                role="output",
                payload_json=run.output_payload,
                created_at=run.completed_at or run.started_at,
            )

        for summary_id, news_id in decision_news_links:
            normalized_summary_id = _try_uuid(summary_id)
            normalized_news_id = _try_uuid(news_id)
            if normalized_summary_id is None or normalized_news_id is None:
                continue
            self._db.execute(
                """
                INSERT INTO decision_news_links
                    (decision_id, summary_id, news_id, linked_at)
                VALUES
                    (:decision_id, :summary_id, :news_id, :linked_at)
                ON CONFLICT (decision_id, summary_id, news_id)
                DO NOTHING
                """,
                {
                    "decision_id": normalized_decision_id,
                    "summary_id": normalized_summary_id,
                    "news_id": normalized_news_id,
                    "linked_at": created_at,
                },
            )

    async def read_decision_trace(self, *, decision_id: str) -> DecisionTraceRecord | None:
        row = self._db.fetchone(
            """
            SELECT decision_id, trace_id, strategy_id, mode, status, started_at, completed_at
            FROM decision_traces
            WHERE decision_id = :decision_id
            """,
            {"decision_id": _coerce_uuid(decision_id)},
        )
        if row is None:
            return None
        return DecisionTraceRecord(
            decision_id=str(row["decision_id"]),
            trace_id=str(row["trace_id"]),
            strategy_id=str(row["strategy_id"]),
            mode=str(row["mode"]),
            status=str(row["status"]),
            started_at=str(row["started_at"]),
            completed_at=str(row["completed_at"]) if row.get("completed_at") else None,
        )

    async def list_agent_runs(self, *, decision_id: str) -> Sequence[AgentRunRecord]:
        rows = self._db.fetchall(
            """
            SELECT agent_run_id, decision_id, agent_name, input_ref, output_ref, latency_ms, status, started_at, completed_at
            FROM agent_runs
            WHERE decision_id = :decision_id
            ORDER BY started_at ASC, agent_run_id ASC
            """,
            {"decision_id": _coerce_uuid(decision_id)},
        )
        return tuple(
            AgentRunRecord(
                agent_run_id=str(row["agent_run_id"]),
                decision_id=str(row["decision_id"]),
                agent_name=str(row["agent_name"]),
                input_ref=str(row["input_ref"]) if row.get("input_ref") else None,
                output_ref=str(row["output_ref"]) if row.get("output_ref") else None,
                latency_ms=float(row["latency_ms"]) if row.get("latency_ms") is not None else None,
                status=str(row["status"]),
                started_at=str(row["started_at"]),
                completed_at=str(row["completed_at"]) if row.get("completed_at") else None,
            )
            for row in rows
        )

    async def list_agent_messages(self, *, agent_run_id: str) -> Sequence[AgentMessageRecord]:
        rows = self._db.fetchall(
            """
            SELECT message_id, agent_run_id, role, payload_json, created_at
            FROM agent_messages
            WHERE agent_run_id = :agent_run_id
            ORDER BY created_at ASC, message_id ASC
            """,
            {"agent_run_id": agent_run_id},
        )
        return tuple(
            AgentMessageRecord(
                message_id=str(row["message_id"]),
                agent_run_id=str(row["agent_run_id"]),
                role=str(row["role"]),
                payload_json=_parse_json_mapping(row.get("payload_json")),
                created_at=str(row["created_at"]),
            )
            for row in rows
        )

    async def list_llm_calls(self, *, decision_id: str) -> Sequence[LLMCallRecord]:
        rows = self._db.fetchall(
            """
            SELECT llm_call_id, trace_id, decision_id, strategy_id, agent_name, provider, model,
                   prompt_payload, response_payload, prompt_tokens, completion_tokens, total_tokens,
                   latency_ms, estimated_cost, created_at
            FROM llm_calls
            WHERE decision_id = :decision_id
            ORDER BY created_at ASC, llm_call_id ASC
            """,
            {"decision_id": _coerce_uuid(decision_id)},
        )
        return tuple(
            LLMCallRecord(
                llm_call_id=str(row["llm_call_id"]),
                trace_id=str(row["trace_id"]),
                decision_id=str(row["decision_id"]),
                strategy_id=str(row["strategy_id"]),
                agent_name=str(row["agent_name"]),
                provider=str(row["provider"]),
                model=str(row["model"]),
                prompt_payload=_parse_json_mapping(row.get("prompt_payload")),
                response_payload=_parse_json_mapping(row.get("response_payload")),
                prompt_tokens=int(row.get("prompt_tokens", 0) or 0),
                completion_tokens=int(row.get("completion_tokens", 0) or 0),
                total_tokens=int(row.get("total_tokens", 0) or 0),
                latency_ms=float(row.get("latency_ms", 0.0) or 0.0),
                estimated_cost=float(row.get("estimated_cost", 0.0) or 0.0),
                created_at=str(row["created_at"]),
            )
            for row in rows
        )

    def _persist_agent_message(
        self,
        *,
        agent_run_id: str,
        role: str,
        payload_json: Mapping[str, Any],
        created_at: str,
    ) -> None:
        self._db.execute(
            """
            INSERT INTO agent_messages
                (message_id, agent_run_id, role, payload_json, created_at)
            VALUES
                (:message_id, :agent_run_id, :role, :payload_json, :created_at)
            ON CONFLICT (message_id)
            DO NOTHING
            """,
            {
                "message_id": str(uuid.uuid4()),
                "agent_run_id": agent_run_id,
                "role": role,
                "payload_json": json.dumps(dict(payload_json), ensure_ascii=True),
                "created_at": created_at,
            },
        )

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS decision_traces (
                decision_id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT NULL,
                created_at TEXT NOT NULL
            )
            """,
            {},
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_runs (
                agent_run_id TEXT PRIMARY KEY,
                decision_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                input_ref TEXT NULL,
                output_ref TEXT NULL,
                latency_ms REAL NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT NULL,
                created_at TEXT NOT NULL
            )
            """,
            {},
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_messages (
                message_id TEXT PRIMARY KEY,
                agent_run_id TEXT NOT NULL,
                role TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            {},
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS decision_news_links (
                decision_id TEXT NOT NULL,
                summary_id TEXT NOT NULL,
                news_id TEXT NOT NULL,
                linked_at TEXT NOT NULL,
                PRIMARY KEY (decision_id, summary_id, news_id)
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
        raise TypeError(
            "connection must be sqlite3.Connection, sqlalchemy.Engine, or sqlalchemy.Connection"
        )

    def execute(self, statement: str, params: Mapping[str, Any]) -> None:
        if self._sqlite_connection is not None:
            self._sqlite_connection.execute(statement, dict(params))
            self._sqlite_connection.commit()
            return
        if self._engine is None:
            raise RuntimeError("store connection was not initialized with a valid bind")
        with self._engine.begin() as connection:
            connection.execute(text(statement), dict(params))

    def fetchone(self, statement: str, params: Mapping[str, Any]) -> Mapping[str, Any] | None:
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

    def fetchall(self, statement: str, params: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        if self._sqlite_connection is not None:
            rows = self._sqlite_connection.execute(statement, dict(params)).fetchall()
            return [dict(row) for row in rows]
        if self._engine is None:
            raise RuntimeError("store connection was not initialized with a valid bind")
        with self._engine.connect() as connection:
            rows = connection.execute(text(statement), dict(params)).mappings().all()
            return [dict(row) for row in rows]


def _parse_json_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, Mapping):
        return dict(parsed)
    return {}


def _coerce_uuid(value: str) -> str:
    raw = value.strip()
    if not raw:
        return str(uuid.uuid4())
    parsed = _try_uuid(raw)
    if parsed is not None:
        return parsed
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))


def _try_uuid(value: str) -> str | None:
    raw = value.strip()
    if not raw:
        return None
    try:
        return str(uuid.UUID(raw))
    except ValueError:
        return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
