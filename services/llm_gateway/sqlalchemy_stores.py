from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3

from services.llm_gateway.persistence import LLMCallRecord
from services.llm_gateway.quota import LLMQuotaStore, QuotaLimits, QuotaUsage


class SQLiteLLMCallStore:
    def __init__(self, *, connection: sqlite3.Connection, ensure_schema: bool = True) -> None:
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        if ensure_schema:
            self._ensure_schema()

    async def persist_call(self, record: LLMCallRecord) -> None:
        self.connection.execute(
            """
            INSERT INTO llm_calls
                (llm_call_id, trace_id, decision_id, strategy_id, agent_name, provider, model,
                 prompt_payload, response_payload, prompt_tokens, completion_tokens, total_tokens,
                 latency_ms, estimated_cost, created_at)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.llm_call_id,
                record.trace_id,
                record.decision_id,
                record.strategy_id,
                record.agent_name,
                record.provider,
                record.model,
                json.dumps(record.prompt_payload, ensure_ascii=True),
                json.dumps(record.response_payload, ensure_ascii=True),
                int(record.prompt_tokens),
                int(record.completion_tokens),
                int(record.total_tokens),
                float(record.latency_ms),
                float(record.estimated_cost),
                record.created_at,
            ),
        )
        self.connection.commit()

    def _ensure_schema(self) -> None:
        self.connection.execute(
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
            """
        )
        self.connection.commit()


class SQLiteLLMQuotaStore(LLMQuotaStore):
    def __init__(self, *, connection: sqlite3.Connection, ensure_schema: bool = True) -> None:
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        if ensure_schema:
            self._ensure_schema()

    async def get_limits(self, *, strategy_id: str, agent_name: str) -> QuotaLimits:
        row = self.connection.execute(
            """
            SELECT daily_token_limit, monthly_cost_limit, is_hard_limit
            FROM llm_quota_limits
            WHERE strategy_id = ? AND agent_name = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (strategy_id, agent_name),
        ).fetchone()
        if row is None:
            return QuotaLimits(daily_token_limit=None, monthly_cost_limit=None, is_hard_limit=False)
        return QuotaLimits(
            daily_token_limit=int(row["daily_token_limit"]) if row["daily_token_limit"] is not None else None,
            monthly_cost_limit=float(row["monthly_cost_limit"])
            if row["monthly_cost_limit"] is not None
            else None,
            is_hard_limit=bool(row["is_hard_limit"]),
        )

    async def get_usage(self, *, strategy_id: str, agent_name: str) -> QuotaUsage:
        now = datetime.now(timezone.utc)
        daily_row = self.connection.execute(
            """
            SELECT total_tokens
            FROM llm_usage_daily
            WHERE strategy_id = ? AND agent_name = ? AND date = ?
            """,
            (strategy_id, agent_name, now.date().isoformat()),
        ).fetchone()
        monthly_row = self.connection.execute(
            """
            SELECT estimated_cost
            FROM llm_usage_monthly
            WHERE strategy_id = ? AND agent_name = ? AND month = ?
            """,
            (strategy_id, agent_name, now.strftime("%Y-%m")),
        ).fetchone()
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

        self.connection.execute(
            """
            INSERT INTO llm_usage_daily (strategy_id, agent_name, date, total_tokens, estimated_cost, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (strategy_id, agent_name, date)
            DO UPDATE SET
                total_tokens = llm_usage_daily.total_tokens + excluded.total_tokens,
                estimated_cost = llm_usage_daily.estimated_cost + excluded.estimated_cost
            """,
            (strategy_id, agent_name, date_key, int(added_tokens), float(added_cost), created_at),
        )
        self.connection.execute(
            """
            INSERT INTO llm_usage_monthly (strategy_id, agent_name, month, total_tokens, estimated_cost, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (strategy_id, agent_name, month)
            DO UPDATE SET
                total_tokens = llm_usage_monthly.total_tokens + excluded.total_tokens,
                estimated_cost = llm_usage_monthly.estimated_cost + excluded.estimated_cost
            """,
            (strategy_id, agent_name, month_key, int(added_tokens), float(added_cost), created_at),
        )
        self.connection.commit()
        return await self.get_usage(strategy_id=strategy_id, agent_name=agent_name)

    def _ensure_schema(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_quota_limits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                daily_token_limit INTEGER NOT NULL,
                monthly_cost_limit REAL NOT NULL,
                is_hard_limit INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(strategy_id, agent_name)
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_usage_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                date TEXT NOT NULL,
                total_tokens INTEGER NOT NULL,
                estimated_cost REAL NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(strategy_id, agent_name, date)
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_usage_monthly (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                month TEXT NOT NULL,
                total_tokens INTEGER NOT NULL,
                estimated_cost REAL NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(strategy_id, agent_name, month)
            )
            """
        )
        self.connection.commit()


# Backward-compatible aliases for previous contract naming.
SQLAlchemyLLMCallStore = SQLiteLLMCallStore
SQLAlchemyLLMQuotaStore = SQLiteLLMQuotaStore
