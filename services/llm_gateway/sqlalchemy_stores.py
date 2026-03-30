from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
import json
import sqlite3

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from services.llm_gateway.persistence import LLMCallRecord
from services.llm_gateway.quota import LLMQuotaStore, QuotaLimits, QuotaUsage


class SQLiteLLMCallStore:
    def __init__(
        self, *, connection: sqlite3.Connection | Engine | Connection, ensure_schema: bool = True
    ) -> None:
        self._db = _StoreConnection(connection=connection)
        if ensure_schema:
            self._ensure_schema()

    async def persist_call(self, record: LLMCallRecord) -> None:
        self._db.execute(
            """
            INSERT INTO llm_calls
                (llm_call_id, trace_id, decision_id, strategy_id, agent_name, provider, model,
                 prompt_payload, response_payload, prompt_tokens, completion_tokens, total_tokens,
                 latency_ms, estimated_cost, created_at)
            VALUES
                (:llm_call_id, :trace_id, :decision_id, :strategy_id, :agent_name, :provider, :model,
                 :prompt_payload, :response_payload, :prompt_tokens, :completion_tokens, :total_tokens,
                 :latency_ms, :estimated_cost, :created_at)
            """,
            {
                "llm_call_id": record.llm_call_id,
                "trace_id": record.trace_id,
                "decision_id": record.decision_id,
                "strategy_id": record.strategy_id,
                "agent_name": record.agent_name,
                "provider": record.provider,
                "model": record.model,
                "prompt_payload": json.dumps(record.prompt_payload, ensure_ascii=True),
                "response_payload": json.dumps(record.response_payload, ensure_ascii=True),
                "prompt_tokens": int(record.prompt_tokens),
                "completion_tokens": int(record.completion_tokens),
                "total_tokens": int(record.total_tokens),
                "latency_ms": float(record.latency_ms),
                "estimated_cost": float(record.estimated_cost),
                "created_at": record.created_at,
            },
        )

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_calls (
                llm_call_id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                decision_id TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_payload TEXT NOT NULL,
                response_payload TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL,
                completion_tokens INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL,
                latency_ms REAL NOT NULL,
                estimated_cost REAL NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            {},
        )


class SQLiteLLMQuotaStore(LLMQuotaStore):
    def __init__(
        self, *, connection: sqlite3.Connection | Engine | Connection, ensure_schema: bool = True
    ) -> None:
        self._db = _StoreConnection(connection=connection)
        if ensure_schema:
            self._ensure_schema()

    async def get_limits(self, *, strategy_id: str, agent_name: str) -> QuotaLimits:
        row = self._db.fetchone(
            """
            SELECT daily_token_limit, monthly_cost_limit, is_hard_limit
            FROM llm_quota_limits
            WHERE strategy_id = :strategy_id AND agent_name = :agent_name
            ORDER BY created_at DESC
            LIMIT 1
            """,
            {"strategy_id": strategy_id, "agent_name": agent_name},
        )
        if row is None:
            return QuotaLimits(daily_token_limit=None, monthly_cost_limit=None, is_hard_limit=False)
        return QuotaLimits(
            daily_token_limit=int(row["daily_token_limit"])
            if row["daily_token_limit"] is not None
            else None,
            monthly_cost_limit=float(row["monthly_cost_limit"])
            if row["monthly_cost_limit"] is not None
            else None,
            is_hard_limit=bool(row["is_hard_limit"]),
        )

    async def get_usage(self, *, strategy_id: str, agent_name: str) -> QuotaUsage:
        now = datetime.now(timezone.utc)
        daily_row = self._db.fetchone(
            """
            SELECT total_tokens
            FROM llm_usage_daily
            WHERE strategy_id = :strategy_id AND agent_name = :agent_name AND date = :date_key
            """,
            {
                "strategy_id": strategy_id,
                "agent_name": agent_name,
                "date_key": now.date().isoformat(),
            },
        )
        monthly_row = self._db.fetchone(
            """
            SELECT estimated_cost
            FROM llm_usage_monthly
            WHERE strategy_id = :strategy_id AND agent_name = :agent_name AND month = :month_key
            """,
            {
                "strategy_id": strategy_id,
                "agent_name": agent_name,
                "month_key": now.strftime("%Y-%m"),
            },
        )
        return QuotaUsage(
            daily_tokens=int(daily_row["total_tokens"]) if daily_row else 0,
            monthly_cost=float(monthly_row["estimated_cost"]) if monthly_row else 0.0,
        )

    async def increment_usage(
        self,
        *,
        strategy_id: str,
        agent_name: str,
        added_tokens: int,
        added_cost: float,
    ) -> QuotaUsage:
        now = datetime.now(timezone.utc)
        date_key = now.date().isoformat()
        month_key = now.strftime("%Y-%m")
        created_at = now.isoformat().replace("+00:00", "Z")

        self._db.execute(
            """
            INSERT INTO llm_usage_daily (strategy_id, agent_name, date, total_tokens, estimated_cost, created_at)
            VALUES (:strategy_id, :agent_name, :date_key, :added_tokens, :added_cost, :created_at)
            ON CONFLICT (strategy_id, agent_name, date)
            DO UPDATE SET
                total_tokens = llm_usage_daily.total_tokens + excluded.total_tokens,
                estimated_cost = llm_usage_daily.estimated_cost + excluded.estimated_cost
            """,
            {
                "strategy_id": strategy_id,
                "agent_name": agent_name,
                "date_key": date_key,
                "added_tokens": int(added_tokens),
                "added_cost": float(added_cost),
                "created_at": created_at,
            },
        )
        self._db.execute(
            """
            INSERT INTO llm_usage_monthly (strategy_id, agent_name, month, total_tokens, estimated_cost, created_at)
            VALUES (:strategy_id, :agent_name, :month_key, :added_tokens, :added_cost, :created_at)
            ON CONFLICT (strategy_id, agent_name, month)
            DO UPDATE SET
                total_tokens = llm_usage_monthly.total_tokens + excluded.total_tokens,
                estimated_cost = llm_usage_monthly.estimated_cost + excluded.estimated_cost
            """,
            {
                "strategy_id": strategy_id,
                "agent_name": agent_name,
                "month_key": month_key,
                "added_tokens": int(added_tokens),
                "added_cost": float(added_cost),
                "created_at": created_at,
            },
        )
        return await self.get_usage(strategy_id=strategy_id, agent_name=agent_name)

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_quota_limits (
                strategy_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                daily_token_limit INTEGER NOT NULL,
                monthly_cost_limit REAL NOT NULL,
                is_hard_limit INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (strategy_id, agent_name)
            )
            """,
            {},
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_usage_daily (
                strategy_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                date TEXT NOT NULL,
                total_tokens INTEGER NOT NULL,
                estimated_cost REAL NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (strategy_id, agent_name, date)
            )
            """,
            {},
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_usage_monthly (
                strategy_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                month TEXT NOT NULL,
                total_tokens INTEGER NOT NULL,
                estimated_cost REAL NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (strategy_id, agent_name, month)
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


# Backward-compatible aliases for previous contract naming.
SQLAlchemyLLMCallStore = SQLiteLLMCallStore
SQLAlchemyLLMQuotaStore = SQLiteLLMQuotaStore
