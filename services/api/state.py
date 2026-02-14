from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid
from typing import Any, Sequence

from services.agent_orchestrator.memory_layer import DecisionMemoryRecord
from services.agent_orchestrator.replay_service import (
    AgentMessageRecord,
    AgentRunRecord,
    DecisionReplayResult,
    DecisionReplayService,
    DecisionTraceRecord,
)
from services.llm_gateway.persistence import LLMCallRecord
from services.oms import PortfolioSnapshot, PositionState, ReconciliationOrder, RiskControlEvent, RiskControlPlane

_VALID_MODES = {"MOCK", "REAL"}
_VALID_STATES = {"ENABLED", "DISABLED", "PAUSED"}


@dataclass(frozen=True, slots=True)
class StrategyRuntimeRecord:
    strategy_id: str
    symbol: str
    mode: str
    state: str
    updated_at: str
    changed_by: str
    reason: str | None


@dataclass(frozen=True, slots=True)
class ModeAuditRecord:
    event_id: str
    mode: str
    changed_by: str
    reason: str
    changed_at: str


@dataclass(frozen=True, slots=True)
class LLMUsageRecord:
    strategy_id: str
    agent_name: str
    daily_tokens: int
    monthly_cost: float
    total_calls: int
    breach_count: int
    daily_token_limit: int | None
    monthly_cost_limit: float | None
    is_hard_limit: bool
    daily_utilization_ratio: float | None
    monthly_utilization_ratio: float | None
    window_date: str
    window_month: str


@dataclass(frozen=True, slots=True)
class LLMBreachRecord:
    llm_call_id: str
    strategy_id: str
    agent_name: str
    trace_id: str
    decision_id: str
    reason: str
    projected_tokens: int | None
    projected_cost: float | None
    created_at: str


@dataclass(frozen=True, slots=True)
class ReplayRequestRecord:
    request_id: str
    decision_id: str
    status: str
    requested_by: str
    requested_at: str
    result: DecisionReplayResult


@dataclass(slots=True)
class ControlPlaneState:
    mode: str
    strategies: dict[str, StrategyRuntimeRecord] = field(default_factory=dict)
    mode_history: list[ModeAuditRecord] = field(default_factory=list)
    orders: list[ReconciliationOrder] = field(default_factory=list)
    positions: list[PositionState] = field(default_factory=list)
    portfolio_snapshots: list[PortfolioSnapshot] = field(default_factory=list)
    risk_controls: RiskControlPlane = field(default_factory=RiskControlPlane)
    risk_events: list[RiskControlEvent] = field(default_factory=list)

    llm_call_records: list[LLMCallRecord] = field(default_factory=list)
    llm_quota_limits: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    replay_traces: dict[str, DecisionTraceRecord] = field(default_factory=dict)
    replay_agent_runs: dict[str, list[AgentRunRecord]] = field(default_factory=dict)
    replay_agent_messages: dict[str, list[AgentMessageRecord]] = field(default_factory=dict)
    replay_llm_calls: dict[str, list[LLMCallRecord]] = field(default_factory=dict)
    replay_summaries: dict[str, DecisionMemoryRecord] = field(default_factory=dict)
    replay_requests: dict[str, ReplayRequestRecord] = field(default_factory=dict)

    def set_mode(self, *, mode: str, actor: str, reason: str) -> tuple[bool, str]:
        normalized_mode = _normalize_mode(mode)
        changed = normalized_mode != self.mode
        self.mode = normalized_mode

        if not changed:
            return False, _utc_now_iso()

        now = _utc_now_iso()
        self.strategies = {
            strategy_id: StrategyRuntimeRecord(
                strategy_id=record.strategy_id,
                symbol=record.symbol,
                mode=normalized_mode,
                state=record.state,
                updated_at=now,
                changed_by=actor,
                reason=reason,
            )
            for strategy_id, record in self.strategies.items()
        }
        self.mode_history.insert(
            0,
            ModeAuditRecord(
                event_id=str(uuid.uuid4()),
                mode=normalized_mode,
                changed_by=actor,
                reason=reason,
                changed_at=now,
            ),
        )
        return True, now

    def list_strategies(self) -> tuple[StrategyRuntimeRecord, ...]:
        return tuple(self.strategies[key] for key in sorted(self.strategies.keys()))

    def list_mode_history(self, *, limit: int = 50) -> tuple[ModeAuditRecord, ...]:
        safe_limit = max(1, int(limit))
        return tuple(self.mode_history[:safe_limit])

    def set_strategy_state(
        self,
        *,
        strategy_id: str,
        state: str,
        actor: str,
        reason: str,
    ) -> StrategyRuntimeRecord:
        normalized_state = _normalize_strategy_state(state)
        key = strategy_id.strip()
        if not key:
            raise ValueError("strategy_id must be non-empty")

        existing = self.strategies.get(key)
        symbol = existing.symbol if existing is not None else _default_symbol(strategy_id=key)
        updated = StrategyRuntimeRecord(
            strategy_id=key,
            symbol=symbol,
            mode=self.mode,
            state=normalized_state,
            updated_at=_utc_now_iso(),
            changed_by=actor,
            reason=reason,
        )
        self.strategies[key] = updated
        return updated

    def list_orders(self, *, status: str | None = None, mode: str | None = None) -> tuple[ReconciliationOrder, ...]:
        status_filter = status.strip().upper() if status else None
        mode_filter = mode.strip().upper() if mode else None
        items: list[ReconciliationOrder] = []
        for order in self.orders:
            if status_filter and order.status.strip().upper() != status_filter:
                continue
            if mode_filter and order.mode.strip().upper() != mode_filter:
                continue
            items.append(order)
        return tuple(items)

    def list_positions(self, *, mode: str | None = None, symbol: str | None = None) -> tuple[PositionState, ...]:
        mode_filter = mode.strip().upper() if mode else None
        symbol_filter = symbol.strip().upper() if symbol else None
        items: list[PositionState] = []
        for position in self.positions:
            if mode_filter and position.mode.strip().upper() != mode_filter:
                continue
            if symbol_filter and position.symbol.strip().upper() != symbol_filter:
                continue
            items.append(position)
        return tuple(items)

    def latest_snapshot(self, *, mode: str | None = None) -> PortfolioSnapshot | None:
        if mode is None:
            candidates = self.portfolio_snapshots
        else:
            target_mode = mode.strip().upper()
            candidates = [
                snapshot
                for snapshot in self.portfolio_snapshots
                if snapshot.mode.strip().upper() == target_mode
            ]

        if not candidates:
            return None

        return max(candidates, key=lambda snapshot: snapshot.snapshot_time)

    def risk_status(self) -> tuple[dict[str, object], tuple[RiskControlEvent, ...]]:
        snapshot = self.risk_controls.snapshot()
        gate = self.risk_controls.evaluate_order_allowed()
        recent = self._capture_risk_events()
        return (
            {
                "kill_switch_enabled": snapshot.kill_switch_enabled,
                "circuit_breaker_open": snapshot.circuit_breaker_open,
                "consecutive_failures": snapshot.consecutive_failures,
                "circuit_breaker_open_until": snapshot.circuit_breaker_open_until,
                "blocked_by": list(gate.blocked_by),
            },
            recent,
        )

    def trip_circuit_breaker(
        self,
        *,
        reason: str,
        actor: str,
        cooldown_seconds: int | None = None,
    ) -> RiskControlEvent:
        self.risk_controls.trip_circuit_breaker(reason=reason, actor=actor, cooldown_seconds=cooldown_seconds)
        return self._last_risk_event()

    def reset_circuit_breaker(self, *, reason: str, actor: str) -> RiskControlEvent:
        self.risk_controls.reset_circuit_breaker(reason=reason, actor=actor)
        return self._last_risk_event()

    def enable_kill_switch(self, *, reason: str, actor: str) -> RiskControlEvent:
        self.risk_controls.enable_kill_switch(reason=reason, actor=actor)
        return self._last_risk_event()

    def disable_kill_switch(self, *, reason: str, actor: str) -> RiskControlEvent:
        self.risk_controls.disable_kill_switch(reason=reason, actor=actor)
        return self._last_risk_event()

    def list_llm_usage(
        self,
        *,
        strategy_id: str | None = None,
        agent_name: str | None = None,
        now: datetime | None = None,
    ) -> tuple[LLMUsageRecord, ...]:
        now_utc = _to_utc(now)
        date_window = now_utc.date().isoformat()
        month_window = now_utc.strftime("%Y-%m")

        grouped: dict[tuple[str, str], dict[str, float | int]] = {}
        for record in self.llm_call_records:
            key = (record.strategy_id, record.agent_name)
            aggregate = grouped.setdefault(
                key,
                {"daily_tokens": 0, "monthly_cost": 0.0, "total_calls": 0, "breach_count": 0},
            )

            aggregate["total_calls"] = int(aggregate["total_calls"]) + 1
            if record.created_at.startswith(date_window):
                aggregate["daily_tokens"] = int(aggregate["daily_tokens"]) + int(record.total_tokens)
            if record.created_at.startswith(month_window):
                aggregate["monthly_cost"] = float(aggregate["monthly_cost"]) + float(record.estimated_cost)

            status = str(record.response_payload.get("status", "")).strip().lower()
            if status == "quota_blocked":
                aggregate["breach_count"] = int(aggregate["breach_count"]) + 1

        items: list[LLMUsageRecord] = []
        for key, aggregate in grouped.items():
            current_strategy, current_agent = key
            if strategy_id is not None and current_strategy != strategy_id:
                continue
            if agent_name is not None and current_agent != agent_name:
                continue

            limit_payload = self.llm_quota_limits.get(key, {})
            daily_limit = _optional_int(limit_payload.get("daily_token_limit"))
            monthly_limit = _optional_float(limit_payload.get("monthly_cost_limit"))
            hard_limit = bool(limit_payload.get("is_hard_limit", False))

            daily_tokens = int(aggregate["daily_tokens"])
            monthly_cost = float(aggregate["monthly_cost"])

            items.append(
                LLMUsageRecord(
                    strategy_id=current_strategy,
                    agent_name=current_agent,
                    daily_tokens=daily_tokens,
                    monthly_cost=monthly_cost,
                    total_calls=int(aggregate["total_calls"]),
                    breach_count=int(aggregate["breach_count"]),
                    daily_token_limit=daily_limit,
                    monthly_cost_limit=monthly_limit,
                    is_hard_limit=hard_limit,
                    daily_utilization_ratio=_ratio(daily_tokens, daily_limit),
                    monthly_utilization_ratio=_ratio(monthly_cost, monthly_limit),
                    window_date=date_window,
                    window_month=month_window,
                )
            )

        items.sort(key=lambda item: (item.strategy_id, item.agent_name))
        return tuple(items)

    def list_llm_breaches(
        self,
        *,
        strategy_id: str | None = None,
        agent_name: str | None = None,
        limit: int = 50,
    ) -> tuple[LLMBreachRecord, ...]:
        safe_limit = max(1, int(limit))
        items: list[LLMBreachRecord] = []
        for record in self.llm_call_records:
            status = str(record.response_payload.get("status", "")).strip().lower()
            if status != "quota_blocked":
                continue
            if strategy_id is not None and record.strategy_id != strategy_id:
                continue
            if agent_name is not None and record.agent_name != agent_name:
                continue

            reason = str(record.response_payload.get("reason", "unknown_quota_block"))
            projected_tokens = _optional_int(record.response_payload.get("projected_tokens"))
            projected_cost = _optional_float(record.response_payload.get("projected_cost"))
            items.append(
                LLMBreachRecord(
                    llm_call_id=record.llm_call_id,
                    strategy_id=record.strategy_id,
                    agent_name=record.agent_name,
                    trace_id=record.trace_id,
                    decision_id=record.decision_id,
                    reason=reason,
                    projected_tokens=projected_tokens,
                    projected_cost=projected_cost,
                    created_at=record.created_at,
                )
            )

        items.sort(key=lambda item: item.created_at, reverse=True)
        return tuple(items[:safe_limit])

    async def replay_decision(self, *, decision_id: str) -> DecisionReplayResult:
        service = DecisionReplayService(
            trace_store=_StateReplayTraceStore(self),
            long_term_store=_StateReplayLongTermStore(self),
        )
        return await service.replay_decision(decision_id=decision_id)

    async def submit_replay_request(
        self,
        *,
        decision_id: str,
        requested_by: str,
    ) -> ReplayRequestRecord:
        result = await self.replay_decision(decision_id=decision_id)
        request_id = str(uuid.uuid4())
        record = ReplayRequestRecord(
            request_id=request_id,
            decision_id=decision_id,
            status="COMPLETED",
            requested_by=requested_by,
            requested_at=_utc_now_iso(),
            result=result,
        )
        self.replay_requests[request_id] = record
        return record

    def get_replay_request(self, *, request_id: str) -> ReplayRequestRecord | None:
        return self.replay_requests.get(request_id)

    def list_replay_traces(self) -> tuple[DecisionTraceRecord, ...]:
        traces = list(self.replay_traces.values())
        traces.sort(key=lambda item: item.started_at, reverse=True)
        return tuple(traces)

    def _last_risk_event(self) -> RiskControlEvent:
        events = self._capture_risk_events()
        if not events:
            raise RuntimeError("risk control action did not emit an event")
        return events[-1]

    def _capture_risk_events(self) -> tuple[RiskControlEvent, ...]:
        drained = self.risk_controls.drain_events()
        if drained:
            self.risk_events.extend(drained)
        return drained


class _StateReplayTraceStore:
    def __init__(self, state: ControlPlaneState) -> None:
        self._state = state

    async def read_decision_trace(self, *, decision_id: str) -> DecisionTraceRecord | None:
        return self._state.replay_traces.get(decision_id)

    async def list_agent_runs(self, *, decision_id: str) -> Sequence[AgentRunRecord]:
        return tuple(self._state.replay_agent_runs.get(decision_id, ()))

    async def list_agent_messages(self, *, agent_run_id: str) -> Sequence[AgentMessageRecord]:
        return tuple(self._state.replay_agent_messages.get(agent_run_id, ()))

    async def list_llm_calls(self, *, decision_id: str) -> Sequence[LLMCallRecord]:
        return tuple(self._state.replay_llm_calls.get(decision_id, ()))


class _StateReplayLongTermStore:
    def __init__(self, state: ControlPlaneState) -> None:
        self._state = state

    async def persist_decision_summary(self, record: DecisionMemoryRecord) -> None:
        self._state.replay_summaries[record.decision_id] = record

    async def read_decision_summary(self, *, decision_id: str) -> DecisionMemoryRecord | None:
        return self._state.replay_summaries.get(decision_id)


def build_default_state(*, default_mode: str) -> ControlPlaneState:
    normalized_mode = _normalize_mode(default_mode)
    now = _utc_now_iso()

    strategies = {
        "btc-momentum": StrategyRuntimeRecord(
            strategy_id="btc-momentum",
            symbol="BTC/USDT",
            mode=normalized_mode,
            state="ENABLED",
            updated_at=now,
            changed_by="system",
            reason="bootstrap",
        ),
        "eth-mean-revert": StrategyRuntimeRecord(
            strategy_id="eth-mean-revert",
            symbol="ETH/USDT",
            mode=normalized_mode,
            state="ENABLED",
            updated_at=now,
            changed_by="system",
            reason="bootstrap",
        ),
    }

    llm_quota_limits = {
        ("btc-momentum", "planner"): {
            "daily_token_limit": 5000,
            "monthly_cost_limit": 150.0,
            "is_hard_limit": True,
            "updated_at": now,
        },
        ("btc-momentum", "risk"): {
            "daily_token_limit": 4000,
            "monthly_cost_limit": 120.0,
            "is_hard_limit": True,
            "updated_at": now,
        },
    }

    return ControlPlaneState(
        mode=normalized_mode,
        strategies=strategies,
        mode_history=[
            ModeAuditRecord(
                event_id="bootstrap-mode",
                mode=normalized_mode,
                changed_by="system",
                reason="bootstrap",
                changed_at=now,
            )
        ],
        llm_quota_limits=llm_quota_limits,
    )


def _normalize_mode(mode: str) -> str:
    normalized_mode = mode.strip().upper()
    if normalized_mode not in _VALID_MODES:
        raise ValueError("mode must be MOCK or REAL")
    return normalized_mode


def _normalize_strategy_state(state: str) -> str:
    normalized_state = state.strip().upper()
    if normalized_state not in _VALID_STATES:
        raise ValueError("strategy state must be ENABLED, DISABLED, or PAUSED")
    return normalized_state


def _default_symbol(*, strategy_id: str) -> str:
    lowered = strategy_id.lower()
    if "eth" in lowered:
        return "ETH/USDT"
    return "BTC/USDT"


def _to_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _ratio(value: float | int, limit: float | int | None) -> float | None:
    if limit is None or float(limit) <= 0:
        return None
    return float(value) / float(limit)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
