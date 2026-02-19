from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any
import json
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Engine

from services.agent_orchestrator.memory_layer import DecisionMemoryRecord
from services.agent_orchestrator.replay_service import (
    AgentMessageRecord,
    AgentRunRecord,
    DecisionReplayResult,
    DecisionTraceRecord,
    ReplayGraphEdge,
    ReplayGraphNode,
)
from services.api.state import (
    ControlPlaneState,
    ModeAuditRecord,
    NewsPanelItem,
    NewsPanelSummary,
    NotificationDeliveryRecord,
    NotificationPreferenceRecord,
    NotificationTraceRecord,
    ReplayRequestRecord,
    StrategyRuntimeRecord,
    build_default_state,
)
from services.llm_gateway.persistence import LLMCallRecord
from services.oms import PortfolioSnapshot, PositionState, ReconciliationOrder
from services.shared.runtime.database import create_runtime_engine_from_env


class ControlPlaneRepository:
    """Database-backed repository for API control-plane and dashboard reads/writes."""

    def __init__(self, *, engine: Engine) -> None:
        self.engine = engine
        self._ensure_support_schema()

    @classmethod
    def from_env(cls) -> ControlPlaneRepository:
        return cls(engine=create_runtime_engine_from_env())

    def load_state(self, *, default_mode: str) -> ControlPlaneState:
        state = build_default_state(default_mode=default_mode)

        self._hydrate_mode_and_strategies(state)
        state.orders = self._list_orders(limit=1000)
        state.positions = self._list_positions(limit=1000)
        state.portfolio_snapshots = self._list_portfolio_snapshots(limit=1000)

        state.llm_call_records = self._list_llm_calls(limit=5000)
        state.llm_quota_limits = self._load_llm_quota_limits()

        state.replay_traces = self._load_replay_traces(limit=500)
        state.replay_agent_runs = self._load_replay_agent_runs(
            decision_ids=tuple(state.replay_traces.keys()),
        )
        state.replay_agent_messages = self._load_replay_agent_messages(
            agent_run_ids=tuple(state.replay_agent_runs.keys()),
        )
        state.replay_llm_calls = self._load_replay_llm_calls(
            decision_ids=tuple(state.replay_traces.keys()),
        )
        state.replay_summaries = self._load_replay_summaries(limit=500)
        state.replay_requests = self._load_replay_requests(limit=500)

        state.news_items = self._list_news_items(limit=500)
        state.news_summaries = self._list_news_summaries(limit=200)

        notification_preferences = self._list_notification_preferences()
        if notification_preferences:
            state.notification_preferences = notification_preferences
        state.notification_delivery_logs = self._list_notification_deliveries(limit=500)
        state.notification_trace_spans = self._list_notification_trace_spans(limit=500)
        state.notification_metrics = self._build_notification_metrics(state)
        return state

    def persist_mode_change(
        self,
        *,
        mode: str,
        changed_by: str,
        reason: str,
        changed_at: str,
        strategies: Sequence[StrategyRuntimeRecord],
    ) -> None:
        normalized_mode = mode.strip().upper()
        if normalized_mode not in {"MOCK", "REAL"}:
            raise ValueError("mode must be MOCK or REAL")
        event_id = str(uuid.uuid4())
        self._execute(
            """
            INSERT INTO mode_audit_events
                (event_id, mode, changed_by, reason, changed_at)
            VALUES
                (:event_id, :mode, :changed_by, :reason, :changed_at)
            """,
            {
                "event_id": event_id,
                "mode": normalized_mode,
                "changed_by": changed_by,
                "reason": reason,
                "changed_at": changed_at,
            },
        )
        for item in strategies:
            self.upsert_strategy_state(item)

    def upsert_strategy_state(self, record: StrategyRuntimeRecord) -> None:
        self._execute(
            """
            INSERT INTO strategy_runtime_state
                (strategy_id, symbol, mode, state, updated_at, changed_by, reason)
            VALUES
                (:strategy_id, :symbol, :mode, :state, :updated_at, :changed_by, :reason)
            ON CONFLICT (strategy_id)
            DO UPDATE SET
                symbol = excluded.symbol,
                mode = excluded.mode,
                state = excluded.state,
                updated_at = excluded.updated_at,
                changed_by = excluded.changed_by,
                reason = excluded.reason
            """,
            {
                "strategy_id": record.strategy_id,
                "symbol": record.symbol,
                "mode": record.mode,
                "state": record.state,
                "updated_at": record.updated_at,
                "changed_by": record.changed_by,
                "reason": record.reason,
            },
        )

    def upsert_notification_preference(self, record: NotificationPreferenceRecord) -> None:
        self._execute(
            """
            INSERT INTO notification_preferences
                (user_id, min_severity, gateways_json, strategy_ids_json, event_types_json, updated_at, updated_by)
            VALUES
                (:user_id, :min_severity, :gateways_json, :strategy_ids_json, :event_types_json, :updated_at, :updated_by)
            ON CONFLICT (user_id)
            DO UPDATE SET
                min_severity = excluded.min_severity,
                gateways_json = excluded.gateways_json,
                strategy_ids_json = excluded.strategy_ids_json,
                event_types_json = excluded.event_types_json,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by
            """,
            {
                "user_id": record.user_id,
                "min_severity": record.min_severity,
                "gateways_json": json.dumps(list(record.gateways), ensure_ascii=True),
                "strategy_ids_json": json.dumps(list(record.strategy_ids), ensure_ascii=True),
                "event_types_json": json.dumps(list(record.event_types), ensure_ascii=True),
                "updated_at": record.updated_at,
                "updated_by": record.updated_by,
            },
        )

    def delete_notification_preference(self, *, user_id: str) -> bool:
        deleted = self._execute(
            """
            DELETE FROM notification_preferences
            WHERE user_id = :user_id
            """,
            {"user_id": user_id},
        )
        return deleted > 0

    def persist_notification_delivery(self, record: NotificationDeliveryRecord) -> None:
        self._execute(
            """
            INSERT INTO notification_deliveries
                (notification_event_id, trace_id, decision_id, event_type, severity, gateway, delivery_status, attempt, detail, logged_at)
            VALUES
                (:notification_event_id, :trace_id, :decision_id, :event_type, :severity, :gateway, :delivery_status, :attempt, :detail, :logged_at)
            """,
            {
                "notification_event_id": record.notification_event_id,
                "trace_id": record.trace_id,
                "decision_id": record.decision_id,
                "event_type": record.event_type,
                "severity": record.severity,
                "gateway": record.gateway,
                "delivery_status": record.delivery_status,
                "attempt": int(record.attempt),
                "detail": record.detail,
                "logged_at": record.logged_at,
            },
        )

    def persist_notification_trace_span(self, record: NotificationTraceRecord) -> None:
        self._execute(
            """
            INSERT INTO notification_trace_spans
                (notification_event_id, trace_id, decision_id, stage, status, latency_ms, gateway, attempt, started_at, completed_at)
            VALUES
                (:notification_event_id, :trace_id, :decision_id, :stage, :status, :latency_ms, :gateway, :attempt, :started_at, :completed_at)
            """,
            {
                "notification_event_id": record.notification_event_id,
                "trace_id": record.trace_id,
                "decision_id": record.decision_id,
                "stage": record.stage,
                "status": record.status,
                "latency_ms": float(record.latency_ms),
                "gateway": record.gateway,
                "attempt": record.attempt,
                "started_at": record.started_at,
                "completed_at": record.completed_at,
            },
        )

    def persist_replay_request(self, record: ReplayRequestRecord) -> None:
        self._execute(
            """
            INSERT INTO replay_requests
                (request_id, decision_id, status, requested_by, requested_at, result_json)
            VALUES
                (:request_id, :decision_id, :status, :requested_by, :requested_at, :result_json)
            ON CONFLICT (request_id)
            DO UPDATE SET
                status = excluded.status,
                requested_by = excluded.requested_by,
                requested_at = excluded.requested_at,
                result_json = excluded.result_json
            """,
            {
                "request_id": record.request_id,
                "decision_id": record.decision_id,
                "status": record.status,
                "requested_by": record.requested_by,
                "requested_at": record.requested_at,
                "result_json": json.dumps(_replay_result_to_payload(record.result), ensure_ascii=True),
            },
        )

    def list_market_klines(
        self,
        *,
        symbol: str,
        interval: str,
        exchange: str | None = None,
        limit: int = 120,
    ) -> tuple[dict[str, Any], ...]:
        rows = self._fetchall(
            """
            SELECT time, exchange, symbol, "interval", open, high, low, close, volume, quote_volume, trades
            FROM klines
            WHERE symbol = :symbol
              AND "interval" = :interval
              AND (:exchange IS NULL OR exchange = :exchange)
            ORDER BY time DESC
            LIMIT :limit
            """,
            {
                "symbol": symbol,
                "interval": interval,
                "exchange": exchange,
                "limit": max(1, int(limit)),
            },
        )
        ordered = list(reversed(rows))
        return tuple(
            {
                "time": str(row.get("time", "")),
                "exchange": str(row.get("exchange", "")),
                "symbol": str(row.get("symbol", "")),
                "interval": str(row.get("interval", "")),
                "open": float(row.get("open", 0.0) or 0.0),
                "high": float(row.get("high", 0.0) or 0.0),
                "low": float(row.get("low", 0.0) or 0.0),
                "close": float(row.get("close", 0.0) or 0.0),
                "volume": float(row.get("volume", 0.0) or 0.0),
                "quote_volume": float(row.get("quote_volume", 0.0) or 0.0),
                "trades": int(row.get("trades", 0) or 0),
            }
            for row in ordered
        )

    def latest_orderbook_snapshot(
        self,
        *,
        symbol: str,
        exchange: str | None = None,
    ) -> dict[str, Any] | None:
        row = self._fetchone(
            """
            SELECT snapshot_time, exchange, symbol, bids, asks, best_bid, best_ask, spread_bps
            FROM orderbook_snapshots
            WHERE symbol = :symbol
              AND (:exchange IS NULL OR exchange = :exchange)
            ORDER BY snapshot_time DESC
            LIMIT 1
            """,
            {
                "symbol": symbol,
                "exchange": exchange,
            },
        )
        if row is None:
            return None
        return {
            "snapshot_time": str(row.get("snapshot_time", "")),
            "exchange": str(row.get("exchange", "")),
            "symbol": str(row.get("symbol", "")),
            "best_bid": float(row.get("best_bid", 0.0) or 0.0),
            "best_ask": float(row.get("best_ask", 0.0) or 0.0),
            "spread_bps": float(row.get("spread_bps", 0.0) or 0.0),
            "bids": _safe_json_list(row.get("bids")),
            "asks": _safe_json_list(row.get("asks")),
        }

    def list_portfolio_history(
        self,
        *,
        mode: str | None,
        limit: int = 200,
    ) -> tuple[PortfolioSnapshot, ...]:
        rows = self._fetchall(
            """
            SELECT snapshot_time, mode, total_balance_usd, available_balance_usd, locked_balance_usd, unrealized_pnl, realized_pnl_today
            FROM portfolio_snapshots
            WHERE (:mode IS NULL OR mode = :mode)
            ORDER BY snapshot_time DESC
            LIMIT :limit
            """,
            {
                "mode": mode,
                "limit": max(1, int(limit)),
            },
        )
        return tuple(
            PortfolioSnapshot(
                snapshot_time=str(row.get("snapshot_time", "")),
                mode=str(row.get("mode", "MOCK") or "MOCK"),
                total_balance_usd=float(row.get("total_balance_usd", 0.0) or 0.0),
                available_balance_usd=float(row.get("available_balance_usd", 0.0) or 0.0),
                locked_balance_usd=float(row.get("locked_balance_usd", 0.0) or 0.0),
                unrealized_pnl=float(row.get("unrealized_pnl", 0.0) or 0.0),
                realized_pnl_today=float(row.get("realized_pnl_today", 0.0) or 0.0),
            )
            for row in reversed(rows)
        )

    def list_latest_signals(self, *, limit: int = 50) -> tuple[dict[str, Any], ...]:
        rows = self._fetchall(
            """
            SELECT decision_id, trace_id, strategy_id, mode, status, summary_json, persisted_at
            FROM runtime_decision_memory
            ORDER BY persisted_at DESC
            LIMIT :limit
            """,
            {"limit": max(1, int(limit))},
        )
        items: list[dict[str, Any]] = []
        for row in rows:
            summary = _safe_json_dict(row.get("summary_json"))
            execution_decision = summary.get("execution_decision")
            action = "HOLD"
            quantity = 0.0
            confidence = 0.0
            if isinstance(execution_decision, Mapping):
                action = str(execution_decision.get("action", action))
                quantity = float(execution_decision.get("quantity", quantity) or 0.0)
                confidence = float(execution_decision.get("confidence", confidence) or 0.0)
            items.append(
                {
                    "decision_id": str(row.get("decision_id", "")),
                    "trace_id": str(row.get("trace_id", "")),
                    "strategy_id": str(row.get("strategy_id", "")),
                    "mode": str(row.get("mode", "")),
                    "status": str(row.get("status", "")),
                    "action": action,
                    "quantity": quantity,
                    "confidence": confidence,
                    "created_at": str(row.get("persisted_at", "")),
                }
            )
        return tuple(items)

    def _hydrate_mode_and_strategies(self, state: ControlPlaneState) -> None:
        mode_rows = self._fetchall(
            """
            SELECT event_id, mode, changed_by, reason, changed_at
            FROM mode_audit_events
            ORDER BY changed_at DESC
            LIMIT 500
            """,
            {},
        )
        strategy_rows = self._fetchall(
            """
            SELECT strategy_id, symbol, mode, state, updated_at, changed_by, reason
            FROM strategy_runtime_state
            ORDER BY strategy_id ASC
            """,
            {},
        )
        if mode_rows:
            latest_mode = str(mode_rows[0].get("mode", state.mode)).strip().upper()
            if latest_mode in {"MOCK", "REAL"}:
                state.mode = latest_mode
            state.mode_history = [
                ModeAuditRecord(
                    event_id=str(row.get("event_id", "")),
                    mode=str(row.get("mode", state.mode)).strip().upper(),
                    changed_by=str(row.get("changed_by", "unknown")),
                    reason=str(row.get("reason", "")),
                    changed_at=str(row.get("changed_at", _utc_now_iso())),
                )
                for row in mode_rows
            ]
        if strategy_rows:
            state.strategies = {
                str(row["strategy_id"]): StrategyRuntimeRecord(
                    strategy_id=str(row["strategy_id"]),
                    symbol=str(row.get("symbol", "BTC/USDT")),
                    mode=str(row.get("mode", state.mode)).strip().upper() or state.mode,
                    state=str(row.get("state", "ENABLED")).strip().upper() or "ENABLED",
                    updated_at=str(row.get("updated_at", _utc_now_iso())),
                    changed_by=str(row.get("changed_by", "system")),
                    reason=(str(row.get("reason")) if row.get("reason") is not None else None),
                )
                for row in strategy_rows
            }

    def _list_orders(self, *, limit: int) -> list[ReconciliationOrder]:
        rows = self._fetchall(
            """
            SELECT o.id AS order_id, s.symbol AS symbol, o.mode AS mode, o.status AS status,
                   o.quantity AS requested_quantity, o.filled_quantity AS filled_quantity, o.average_price AS average_price
            FROM orders o
            JOIN symbols s ON s.id = o.symbol_id
            ORDER BY o.updated_at DESC
            LIMIT :limit
            """,
            {"limit": max(1, int(limit))},
        )
        return [
            ReconciliationOrder(
                order_id=str(row.get("order_id", "")),
                symbol=str(row.get("symbol", "")),
                mode=str(row.get("mode", "MOCK") or "MOCK"),
                requested_quantity=float(row.get("requested_quantity", 0.0) or 0.0),
                status=str(row.get("status", "OPEN") or "OPEN"),
                filled_quantity=float(row.get("filled_quantity", 0.0) or 0.0),
                average_price=float(row["average_price"]) if row.get("average_price") is not None else None,
            )
            for row in rows
        ]

    def _list_positions(self, *, limit: int) -> list[PositionState]:
        rows = self._fetchall(
            """
            SELECT p.mode AS mode, s.symbol AS symbol, p.quantity AS quantity, p.entry_price AS average_entry_price,
                   p.realized_pnl AS realized_pnl, p.status AS status, COALESCE(p.closed_at, p.opened_at) AS updated_at
            FROM positions p
            JOIN symbols s ON s.id = p.symbol_id
            ORDER BY COALESCE(p.closed_at, p.opened_at) DESC
            LIMIT :limit
            """,
            {"limit": max(1, int(limit))},
        )
        return [
            PositionState(
                mode=str(row.get("mode", "MOCK") or "MOCK"),
                symbol=str(row.get("symbol", "")),
                quantity=float(row.get("quantity", 0.0) or 0.0),
                average_entry_price=float(row.get("average_entry_price", 0.0) or 0.0),
                realized_pnl=float(row.get("realized_pnl", 0.0) or 0.0),
                status=str(row.get("status", "OPEN") or "OPEN"),
                updated_at=str(row.get("updated_at", _utc_now_iso())),
            )
            for row in rows
        ]

    def _list_portfolio_snapshots(self, *, limit: int) -> list[PortfolioSnapshot]:
        rows = self._fetchall(
            """
            SELECT snapshot_time, mode, total_balance_usd, available_balance_usd, locked_balance_usd, unrealized_pnl, realized_pnl_today
            FROM portfolio_snapshots
            ORDER BY snapshot_time DESC
            LIMIT :limit
            """,
            {"limit": max(1, int(limit))},
        )
        return [
            PortfolioSnapshot(
                snapshot_time=str(row.get("snapshot_time", "")),
                mode=str(row.get("mode", "MOCK") or "MOCK"),
                total_balance_usd=float(row.get("total_balance_usd", 0.0) or 0.0),
                available_balance_usd=float(row.get("available_balance_usd", 0.0) or 0.0),
                locked_balance_usd=float(row.get("locked_balance_usd", 0.0) or 0.0),
                unrealized_pnl=float(row.get("unrealized_pnl", 0.0) or 0.0),
                realized_pnl_today=float(row.get("realized_pnl_today", 0.0) or 0.0),
            )
            for row in rows
        ]

    def _list_llm_calls(self, *, limit: int) -> list[LLMCallRecord]:
        rows = self._fetchall(
            """
            SELECT llm_call_id, trace_id, decision_id, strategy_id, agent_name, provider, model,
                   prompt_payload, response_payload, prompt_tokens, completion_tokens, total_tokens,
                   latency_ms, estimated_cost, created_at
            FROM llm_calls
            ORDER BY created_at DESC
            LIMIT :limit
            """,
            {"limit": max(1, int(limit))},
        )
        return [
            LLMCallRecord(
                llm_call_id=str(row.get("llm_call_id", "")),
                trace_id=str(row.get("trace_id", "")),
                decision_id=str(row.get("decision_id", "")),
                strategy_id=str(row.get("strategy_id", "")),
                agent_name=str(row.get("agent_name", "")),
                provider=str(row.get("provider", "")),
                model=str(row.get("model", "")),
                prompt_payload=_safe_json_dict(row.get("prompt_payload")),
                response_payload=_safe_json_dict(row.get("response_payload")),
                prompt_tokens=int(row.get("prompt_tokens", 0) or 0),
                completion_tokens=int(row.get("completion_tokens", 0) or 0),
                total_tokens=int(row.get("total_tokens", 0) or 0),
                latency_ms=float(row.get("latency_ms", 0.0) or 0.0),
                estimated_cost=float(row.get("estimated_cost", 0.0) or 0.0),
                created_at=str(row.get("created_at", _utc_now_iso())),
            )
            for row in rows
        ]

    def _load_llm_quota_limits(self) -> dict[tuple[str, str], dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT strategy_id, agent_name, daily_token_limit, monthly_cost_limit, is_hard_limit, created_at
            FROM llm_quota_limits
            """,
            {},
        )
        payload: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            strategy_id = str(row.get("strategy_id", ""))
            agent_name = str(row.get("agent_name", ""))
            if not strategy_id or not agent_name:
                continue
            payload[(strategy_id, agent_name)] = {
                "daily_token_limit": int(row.get("daily_token_limit", 0) or 0),
                "monthly_cost_limit": float(row.get("monthly_cost_limit", 0.0) or 0.0),
                "is_hard_limit": bool(row.get("is_hard_limit", True)),
                "updated_at": str(row.get("created_at", _utc_now_iso())),
            }
        return payload

    def _load_replay_traces(self, *, limit: int) -> dict[str, DecisionTraceRecord]:
        rows = self._fetchall(
            """
            SELECT decision_id, trace_id, strategy_id, mode, status, started_at, completed_at
            FROM decision_traces
            ORDER BY started_at DESC
            LIMIT :limit
            """,
            {"limit": max(1, int(limit))},
        )
        return {
            str(row["decision_id"]): DecisionTraceRecord(
                decision_id=str(row.get("decision_id", "")),
                trace_id=str(row.get("trace_id", "")),
                strategy_id=str(row.get("strategy_id", "")),
                mode=str(row.get("mode", "MOCK") or "MOCK"),
                status=str(row.get("status", "")),
                started_at=str(row.get("started_at", _utc_now_iso())),
                completed_at=(
                    str(row.get("completed_at")) if row.get("completed_at") is not None else None
                ),
            )
            for row in rows
        }

    def _load_replay_agent_runs(
        self,
        *,
        decision_ids: Sequence[str],
    ) -> dict[str, list[AgentRunRecord]]:
        if not decision_ids:
            return {}
        rows = self._fetchall(
            """
            SELECT agent_run_id, decision_id, agent_name, input_ref, output_ref, latency_ms, status, started_at, completed_at
            FROM agent_runs
            WHERE decision_id = ANY(:decision_ids)
            ORDER BY started_at ASC
            """,
            {"decision_ids": list(decision_ids)},
        )
        grouped: dict[str, list[AgentRunRecord]] = {}
        for row in rows:
            record = AgentRunRecord(
                agent_run_id=str(row.get("agent_run_id", "")),
                decision_id=str(row.get("decision_id", "")),
                agent_name=str(row.get("agent_name", "")),
                input_ref=(str(row.get("input_ref")) if row.get("input_ref") is not None else None),
                output_ref=(str(row.get("output_ref")) if row.get("output_ref") is not None else None),
                latency_ms=(float(row["latency_ms"]) if row.get("latency_ms") is not None else None),
                status=str(row.get("status", "")),
                started_at=str(row.get("started_at", _utc_now_iso())),
                completed_at=(
                    str(row.get("completed_at")) if row.get("completed_at") is not None else None
                ),
            )
            grouped.setdefault(record.decision_id, []).append(record)
        return grouped

    def _load_replay_agent_messages(
        self,
        *,
        agent_run_ids: Sequence[str],
    ) -> dict[str, list[AgentMessageRecord]]:
        if not agent_run_ids:
            return {}
        rows = self._fetchall(
            """
            SELECT message_id, agent_run_id, role, payload_json, created_at
            FROM agent_messages
            WHERE agent_run_id = ANY(:agent_run_ids)
            ORDER BY created_at ASC
            """,
            {"agent_run_ids": list(agent_run_ids)},
        )
        grouped: dict[str, list[AgentMessageRecord]] = {}
        for row in rows:
            agent_run_id = str(row.get("agent_run_id", ""))
            record = AgentMessageRecord(
                message_id=str(row.get("message_id", "")),
                agent_run_id=agent_run_id,
                role=str(row.get("role", "")),
                payload_json=_safe_json_dict(row.get("payload_json")),
                created_at=str(row.get("created_at", _utc_now_iso())),
            )
            grouped.setdefault(agent_run_id, []).append(record)
        return grouped

    def _load_replay_llm_calls(
        self,
        *,
        decision_ids: Sequence[str],
    ) -> dict[str, list[LLMCallRecord]]:
        if not decision_ids:
            return {}
        rows = self._fetchall(
            """
            SELECT llm_call_id, trace_id, decision_id, strategy_id, agent_name, provider, model,
                   prompt_payload, response_payload, prompt_tokens, completion_tokens, total_tokens,
                   latency_ms, estimated_cost, created_at
            FROM llm_calls
            WHERE decision_id = ANY(:decision_ids)
            ORDER BY created_at ASC
            """,
            {"decision_ids": list(decision_ids)},
        )
        grouped: dict[str, list[LLMCallRecord]] = {}
        for row in rows:
            decision_id = str(row.get("decision_id", ""))
            record = LLMCallRecord(
                llm_call_id=str(row.get("llm_call_id", "")),
                trace_id=str(row.get("trace_id", "")),
                decision_id=decision_id,
                strategy_id=str(row.get("strategy_id", "")),
                agent_name=str(row.get("agent_name", "")),
                provider=str(row.get("provider", "")),
                model=str(row.get("model", "")),
                prompt_payload=_safe_json_dict(row.get("prompt_payload")),
                response_payload=_safe_json_dict(row.get("response_payload")),
                prompt_tokens=int(row.get("prompt_tokens", 0) or 0),
                completion_tokens=int(row.get("completion_tokens", 0) or 0),
                total_tokens=int(row.get("total_tokens", 0) or 0),
                latency_ms=float(row.get("latency_ms", 0.0) or 0.0),
                estimated_cost=float(row.get("estimated_cost", 0.0) or 0.0),
                created_at=str(row.get("created_at", _utc_now_iso())),
            )
            grouped.setdefault(decision_id, []).append(record)
        return grouped

    def _load_replay_summaries(self, *, limit: int) -> dict[str, DecisionMemoryRecord]:
        rows = self._fetchall(
            """
            SELECT decision_id, trace_id, strategy_id, mode, status, summary_json, lifecycle_json, persisted_at
            FROM runtime_decision_memory
            ORDER BY persisted_at DESC
            LIMIT :limit
            """,
            {"limit": max(1, int(limit))},
        )
        payload: dict[str, DecisionMemoryRecord] = {}
        for row in rows:
            decision_id = str(row.get("decision_id", ""))
            summary = _safe_json_dict(row.get("summary_json"))
            lifecycle_payload = _safe_json_list(row.get("lifecycle_json"))
            lifecycle = tuple(item for item in lifecycle_payload if isinstance(item, Mapping))
            payload[decision_id] = DecisionMemoryRecord(
                trace_id=str(row.get("trace_id", "")),
                decision_id=decision_id,
                strategy_id=str(row.get("strategy_id", "")),
                mode=str(row.get("mode", "MOCK") or "MOCK"),
                status=str(row.get("status", "")),
                summary=summary,
                lifecycle=lifecycle,
                persisted_at=str(row.get("persisted_at", _utc_now_iso())),
            )
        return payload

    def _load_replay_requests(self, *, limit: int) -> dict[str, ReplayRequestRecord]:
        rows = self._fetchall(
            """
            SELECT request_id, decision_id, status, requested_by, requested_at, result_json
            FROM replay_requests
            ORDER BY requested_at DESC
            LIMIT :limit
            """,
            {"limit": max(1, int(limit))},
        )
        payload: dict[str, ReplayRequestRecord] = {}
        for row in rows:
            request_id = str(row.get("request_id", "")).strip()
            if not request_id:
                continue
            result_payload = _safe_json_dict(row.get("result_json"))
            payload[request_id] = ReplayRequestRecord(
                request_id=request_id,
                decision_id=str(row.get("decision_id", "")),
                status=str(row.get("status", "COMPLETED")),
                requested_by=str(row.get("requested_by", "unknown")),
                requested_at=str(row.get("requested_at", _utc_now_iso())),
                result=_payload_to_replay_result(result_payload),
            )
        return payload

    def _list_news_items(self, *, limit: int) -> list[NewsPanelItem]:
        rows = self._fetchall(
            """
            SELECT news_id, source, title, url, published_at
            FROM news_items
            ORDER BY published_at DESC
            LIMIT :limit
            """,
            {"limit": max(1, int(limit))},
        )
        tags_rows = self._fetchall(
            """
            SELECT news_id, symbol, topic, relevance_score, sentiment_score, created_at
            FROM news_tags
            ORDER BY created_at DESC
            LIMIT :limit
            """,
            {"limit": max(1, int(limit) * 4)},
        )
        top_tag_by_news: dict[str, Mapping[str, Any]] = {}
        for row in tags_rows:
            news_id = str(row.get("news_id", ""))
            if not news_id or news_id in top_tag_by_news:
                continue
            top_tag_by_news[news_id] = row

        items: list[NewsPanelItem] = []
        for row in rows:
            news_id = str(row.get("news_id", ""))
            tag = top_tag_by_news.get(news_id, {})
            symbol = tag.get("symbol")
            items.append(
                NewsPanelItem(
                    news_id=news_id,
                    source=str(row.get("source", "")),
                    title=str(row.get("title", "")),
                    url=str(row.get("url", "")),
                    published_at=str(row.get("published_at", _utc_now_iso())),
                    symbol=str(symbol) if symbol is not None and str(symbol).strip() else None,
                    topic=str(tag.get("topic", "general") or "general"),
                    relevance_score=float(tag.get("relevance_score", 0.0) or 0.0),
                    sentiment_score=float(tag.get("sentiment_score", 0.0) or 0.0),
                )
            )
        return items

    def _list_news_summaries(self, *, limit: int) -> list[NewsPanelSummary]:
        rows = self._fetchall(
            """
            SELECT summary_id, symbol_scope, window_start, window_end, summary_text, generated_at
            FROM news_summaries
            ORDER BY generated_at DESC
            LIMIT :limit
            """,
            {"limit": max(1, int(limit))},
        )
        summary_sources = self._fetchall(
            """
            SELECT summary_id, news_id
            FROM news_summary_sources
            """,
            {},
        )
        news_ids_by_summary: dict[str, list[str]] = {}
        for row in summary_sources:
            summary_id = str(row.get("summary_id", ""))
            news_id = str(row.get("news_id", ""))
            if not summary_id or not news_id:
                continue
            news_ids_by_summary.setdefault(summary_id, []).append(news_id)

        items: list[NewsPanelSummary] = []
        for row in rows:
            summary_id = str(row.get("summary_id", ""))
            source_news_ids = tuple(news_ids_by_summary.get(summary_id, ()))
            avg_sentiment = self._summary_avg_sentiment(summary_id=summary_id)
            items.append(
                NewsPanelSummary(
                    summary_id=summary_id,
                    symbol_scope=str(row.get("symbol_scope", "GLOBAL") or "GLOBAL"),
                    window_start=str(row.get("window_start", _utc_now_iso())),
                    window_end=str(row.get("window_end", _utc_now_iso())),
                    summary_text=str(row.get("summary_text", "")),
                    generated_at=str(row.get("generated_at", _utc_now_iso())),
                    source_news_ids=source_news_ids,
                    avg_sentiment=avg_sentiment,
                )
            )
        return items

    def _summary_avg_sentiment(self, *, summary_id: str) -> float:
        row = self._fetchone(
            """
            SELECT AVG(t.sentiment_score) AS avg_sentiment
            FROM news_tags t
            WHERE t.news_id IN (
                SELECT s.news_id
                FROM news_summary_sources s
                WHERE s.summary_id = :summary_id
            )
            """,
            {"summary_id": summary_id},
        )
        if row is None:
            return 0.0
        return float(row.get("avg_sentiment", 0.0) or 0.0)

    def _list_notification_preferences(self) -> dict[str, NotificationPreferenceRecord]:
        rows = self._fetchall(
            """
            SELECT user_id, min_severity, gateways_json, strategy_ids_json, event_types_json, updated_at, updated_by
            FROM notification_preferences
            ORDER BY user_id ASC
            """,
            {},
        )
        payload: dict[str, NotificationPreferenceRecord] = {}
        for row in rows:
            user_id = str(row.get("user_id", "")).strip()
            if not user_id:
                continue
            payload[user_id] = NotificationPreferenceRecord(
                user_id=user_id,
                min_severity=str(row.get("min_severity", "INFO")),
                gateways=tuple(str(item) for item in _safe_json_list(row.get("gateways_json")) if str(item).strip()),
                strategy_ids=tuple(str(item) for item in _safe_json_list(row.get("strategy_ids_json")) if str(item).strip()),
                event_types=tuple(str(item) for item in _safe_json_list(row.get("event_types_json")) if str(item).strip()),
                updated_at=str(row.get("updated_at", _utc_now_iso())),
                updated_by=str(row.get("updated_by", "system")),
            )
        return payload

    def _list_notification_deliveries(self, *, limit: int) -> list[NotificationDeliveryRecord]:
        rows = self._fetchall(
            """
            SELECT notification_event_id, trace_id, decision_id, event_type, severity, gateway, delivery_status, attempt, detail, logged_at
            FROM notification_deliveries
            ORDER BY logged_at DESC
            LIMIT :limit
            """,
            {"limit": max(1, int(limit))},
        )
        return [
            NotificationDeliveryRecord(
                notification_event_id=str(row.get("notification_event_id", "")),
                trace_id=str(row.get("trace_id", "")),
                decision_id=str(row.get("decision_id", "")),
                event_type=str(row.get("event_type", "")),
                severity=str(row.get("severity", "INFO")),
                gateway=str(row.get("gateway", "")),
                delivery_status=str(row.get("delivery_status", "")),
                attempt=int(row.get("attempt", 0) or 0),
                detail=(str(row.get("detail")) if row.get("detail") is not None else None),
                logged_at=str(row.get("logged_at", _utc_now_iso())),
            )
            for row in rows
        ]

    def _list_notification_trace_spans(self, *, limit: int) -> list[NotificationTraceRecord]:
        rows = self._fetchall(
            """
            SELECT notification_event_id, trace_id, decision_id, stage, status, latency_ms, gateway, attempt, started_at, completed_at
            FROM notification_trace_spans
            ORDER BY completed_at DESC
            LIMIT :limit
            """,
            {"limit": max(1, int(limit))},
        )
        return [
            NotificationTraceRecord(
                notification_event_id=str(row.get("notification_event_id", "")),
                trace_id=str(row.get("trace_id", "")),
                decision_id=str(row.get("decision_id", "")),
                stage=str(row.get("stage", "")),
                status=str(row.get("status", "")),
                latency_ms=float(row.get("latency_ms", 0.0) or 0.0),
                gateway=(str(row.get("gateway")) if row.get("gateway") is not None else None),
                attempt=(int(row["attempt"]) if row.get("attempt") is not None else None),
                started_at=str(row.get("started_at", _utc_now_iso())),
                completed_at=str(row.get("completed_at", _utc_now_iso())),
            )
            for row in rows
        ]

    def _build_notification_metrics(self, state: ControlPlaneState) -> dict[str, Any]:
        totals = {
            "received_total": 0,
            "filtered_total": 0,
            "dispatched_total": 0,
            "delivered_total": 0,
            "failed_total": 0,
            "retryable_total": 0,
            "dlq_total": 0,
        }
        gateway_status: dict[str, int] = {}
        retry_attempt_histogram: dict[str, int] = {}
        for item in state.notification_delivery_logs:
            totals["dispatched_total"] += 1
            status = item.delivery_status.strip().upper()
            if status == "DELIVERED":
                totals["delivered_total"] += 1
            elif status in {"RETRYABLE", "RETRYABLE_ERROR", "FAILED_RETRYABLE"}:
                totals["retryable_total"] += 1
            else:
                totals["failed_total"] += 1
            gateway_key = f"{item.gateway}:{status}"
            gateway_status[gateway_key] = gateway_status.get(gateway_key, 0) + 1
            attempt_bucket = str(max(1, int(item.attempt)))
            retry_attempt_histogram[attempt_bucket] = retry_attempt_histogram.get(attempt_bucket, 0) + 1
        totals["received_total"] = totals["dispatched_total"]
        return {
            "totals": totals,
            "suppression": {"dedupe": 0, "rate_limit": 0},
            "gateway_status": gateway_status,
            "retry_attempt_histogram": retry_attempt_histogram,
            "generated_at": _utc_now_iso(),
        }

    def _ensure_support_schema(self) -> None:
        statements = (
            """
            CREATE TABLE IF NOT EXISTS strategy_runtime_state (
                strategy_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                mode TEXT NOT NULL,
                state TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                changed_by TEXT NOT NULL,
                reason TEXT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mode_audit_events (
                event_id TEXT PRIMARY KEY,
                mode TEXT NOT NULL,
                changed_by TEXT NOT NULL,
                reason TEXT NOT NULL,
                changed_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS notification_preferences (
                user_id TEXT PRIMARY KEY,
                min_severity TEXT NOT NULL,
                gateways_json TEXT NOT NULL,
                strategy_ids_json TEXT NOT NULL,
                event_types_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS notification_deliveries (
                id BIGSERIAL PRIMARY KEY,
                notification_event_id TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                decision_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                gateway TEXT NOT NULL,
                delivery_status TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                detail TEXT NULL,
                logged_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS notification_trace_spans (
                id BIGSERIAL PRIMARY KEY,
                notification_event_id TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                decision_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                status TEXT NOT NULL,
                latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
                gateway TEXT NULL,
                attempt INTEGER NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS replay_requests (
                request_id TEXT PRIMARY KEY,
                decision_id TEXT NOT NULL,
                status TEXT NOT NULL,
                requested_by TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                result_json TEXT NOT NULL
            )
            """,
        )
        for statement in statements:
            self._execute(statement, {})

    def _execute(self, statement: str, params: Mapping[str, Any]) -> int:
        try:
            with self.engine.begin() as connection:
                result = connection.execute(text(statement), dict(params))
                return int(result.rowcount or 0)
        except Exception:
            return 0

    def _fetchone(self, statement: str, params: Mapping[str, Any]) -> Mapping[str, Any] | None:
        try:
            with self.engine.connect() as connection:
                row = connection.execute(text(statement), dict(params)).mappings().first()
                if row is None:
                    return None
                return dict(row)
        except Exception:
            return None

    def _fetchall(self, statement: str, params: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        try:
            with self.engine.connect() as connection:
                rows = connection.execute(text(statement), dict(params)).mappings().all()
                return [dict(row) for row in rows]
        except Exception:
            return []


def _safe_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str):
        return {}
    text_value = value.strip()
    if not text_value:
        return {}
    try:
        parsed = json.loads(text_value)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, Mapping):
        return dict(parsed)
    return {}


def _safe_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if not isinstance(value, str):
        return []
    text_value = value.strip()
    if not text_value:
        return []
    try:
        parsed = json.loads(text_value)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        return list(parsed)
    return []


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _replay_result_to_payload(result: DecisionReplayResult) -> dict[str, Any]:
    return {
        "decision_id": result.decision_id,
        "trace_id": result.trace_id,
        "strategy_id": result.strategy_id,
        "mode": result.mode,
        "status": result.status,
        "summary": dict(result.summary),
        "lifecycle": [dict(item) for item in result.lifecycle],
        "agent_runs": [dict(item) for item in result.agent_runs],
        "llm_calls": [dict(item) for item in result.llm_calls],
        "graph_nodes": [
            {
                "node_id": node.node_id,
                "node_type": node.node_type,
                "label": node.label,
                "payload": dict(node.payload),
            }
            for node in result.graph_nodes
        ],
        "graph_edges": [
            {
                "from_node_id": edge.from_node_id,
                "to_node_id": edge.to_node_id,
                "relation": edge.relation,
            }
            for edge in result.graph_edges
        ],
        "deterministic_digest": result.deterministic_digest,
    }


def _payload_to_replay_result(payload: Mapping[str, Any]) -> DecisionReplayResult:
    graph_nodes_payload = payload.get("graph_nodes")
    graph_edges_payload = payload.get("graph_edges")
    lifecycle_payload = payload.get("lifecycle")
    agent_runs_payload = payload.get("agent_runs")
    llm_calls_payload = payload.get("llm_calls")

    graph_nodes: list[ReplayGraphNode] = []
    if isinstance(graph_nodes_payload, list):
        for row in graph_nodes_payload:
            if not isinstance(row, Mapping):
                continue
            graph_nodes.append(
                ReplayGraphNode(
                    node_id=str(row.get("node_id", "")),
                    node_type=str(row.get("node_type", "")),
                    label=str(row.get("label", "")),
                    payload=_safe_json_dict(row.get("payload")),
                )
            )

    graph_edges: list[ReplayGraphEdge] = []
    if isinstance(graph_edges_payload, list):
        for row in graph_edges_payload:
            if not isinstance(row, Mapping):
                continue
            graph_edges.append(
                ReplayGraphEdge(
                    from_node_id=str(row.get("from_node_id", "")),
                    to_node_id=str(row.get("to_node_id", "")),
                    relation=str(row.get("relation", "")),
                )
            )

    lifecycle: list[Mapping[str, Any]] = []
    if isinstance(lifecycle_payload, list):
        lifecycle = [dict(row) for row in lifecycle_payload if isinstance(row, Mapping)]

    agent_runs: list[Mapping[str, Any]] = []
    if isinstance(agent_runs_payload, list):
        agent_runs = [dict(row) for row in agent_runs_payload if isinstance(row, Mapping)]

    llm_calls: list[Mapping[str, Any]] = []
    if isinstance(llm_calls_payload, list):
        llm_calls = [dict(row) for row in llm_calls_payload if isinstance(row, Mapping)]

    return DecisionReplayResult(
        decision_id=str(payload.get("decision_id", "")),
        trace_id=str(payload.get("trace_id", "")),
        strategy_id=str(payload.get("strategy_id", "")),
        mode=str(payload.get("mode", "MOCK") or "MOCK"),
        status=str(payload.get("status", "")),
        summary=_safe_json_dict(payload.get("summary")),
        lifecycle=tuple(lifecycle),
        agent_runs=tuple(agent_runs),
        llm_calls=tuple(llm_calls),
        graph_nodes=tuple(graph_nodes),
        graph_edges=tuple(graph_edges),
        deterministic_digest=str(payload.get("deterministic_digest", "")),
    )
