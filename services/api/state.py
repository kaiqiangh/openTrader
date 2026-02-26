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
_VALID_NOTIFICATION_SEVERITIES = {"INFO", "WARNING", "CRITICAL"}


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
class LLMCallLogRecord:
    llm_call_id: str
    trace_id: str
    decision_id: str
    strategy_id: str
    agent_name: str
    provider: str
    model: str
    status: str
    mode: str | None
    tier: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    estimated_cost: float
    created_at: str
    prompt_preview: str | None
    response_preview: str | None


@dataclass(frozen=True, slots=True)
class ReplayRequestRecord:
    request_id: str
    decision_id: str
    status: str
    requested_by: str
    requested_at: str
    result: DecisionReplayResult


@dataclass(frozen=True, slots=True)
class NewsPanelItem:
    news_id: str
    source: str
    title: str
    url: str
    published_at: str
    symbol: str | None
    topic: str
    relevance_score: float
    sentiment_score: float


@dataclass(frozen=True, slots=True)
class NewsPanelSummary:
    summary_id: str
    symbol_scope: str
    window_start: str
    window_end: str
    summary_text: str
    generated_at: str
    source_news_ids: tuple[str, ...]
    avg_sentiment: float


@dataclass(frozen=True, slots=True)
class NewsImpactRecord:
    symbol: str
    headline_count: int
    avg_sentiment: float
    max_relevance: float
    latest_published_at: str | None
    latest_summary: str | None


@dataclass(frozen=True, slots=True)
class NotificationPreferenceRecord:
    user_id: str
    min_severity: str
    gateways: tuple[str, ...]
    strategy_ids: tuple[str, ...]
    event_types: tuple[str, ...]
    updated_at: str
    updated_by: str


@dataclass(frozen=True, slots=True)
class NotificationDeliveryRecord:
    notification_event_id: str
    trace_id: str
    decision_id: str
    event_type: str
    severity: str
    gateway: str
    delivery_status: str
    attempt: int
    detail: str | None
    logged_at: str


@dataclass(frozen=True, slots=True)
class NotificationTraceRecord:
    notification_event_id: str
    trace_id: str
    decision_id: str
    stage: str
    status: str
    latency_ms: float
    gateway: str | None
    attempt: int | None
    started_at: str
    completed_at: str


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
    news_items: list[NewsPanelItem] = field(default_factory=list)
    news_summaries: list[NewsPanelSummary] = field(default_factory=list)
    notification_preferences: dict[str, NotificationPreferenceRecord] = field(default_factory=dict)
    notification_metrics: dict[str, Any] = field(default_factory=dict)
    notification_delivery_logs: list[NotificationDeliveryRecord] = field(default_factory=list)
    notification_trace_spans: list[NotificationTraceRecord] = field(default_factory=list)

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

    def list_llm_call_logs(
        self,
        *,
        strategy_id: str | None = None,
        agent_name: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> tuple[LLMCallLogRecord, ...]:
        safe_limit = max(1, int(limit))
        strategy_filter = strategy_id.strip() if strategy_id else None
        agent_filter = agent_name.strip() if agent_name else None
        status_filter = status.strip().lower() if status else None

        rows: list[LLMCallLogRecord] = []
        for record in self.llm_call_records:
            if strategy_filter and record.strategy_id != strategy_filter:
                continue
            if agent_filter and record.agent_name != agent_filter:
                continue

            response_status = str(record.response_payload.get("status", "succeeded")).strip().lower() or "succeeded"
            if status_filter and response_status != status_filter:
                continue

            metadata = record.prompt_payload.get("metadata", {})
            mode = None
            tier = None
            if isinstance(metadata, dict):
                mode_value = metadata.get("mode")
                tier_value = metadata.get("tier")
                mode = str(mode_value) if mode_value is not None else None
                tier = str(tier_value) if tier_value is not None else None

            rows.append(
                LLMCallLogRecord(
                    llm_call_id=record.llm_call_id,
                    trace_id=record.trace_id,
                    decision_id=record.decision_id,
                    strategy_id=record.strategy_id,
                    agent_name=record.agent_name,
                    provider=record.provider,
                    model=record.model,
                    status=response_status,
                    mode=mode,
                    tier=tier,
                    prompt_tokens=int(record.prompt_tokens),
                    completion_tokens=int(record.completion_tokens),
                    total_tokens=int(record.total_tokens),
                    latency_ms=float(record.latency_ms),
                    estimated_cost=float(record.estimated_cost),
                    created_at=record.created_at,
                    prompt_preview=_extract_prompt_preview(record.prompt_payload),
                    response_preview=_extract_response_preview(record.response_payload),
                )
            )

        rows.sort(key=lambda item: item.created_at, reverse=True)
        return tuple(rows[:safe_limit])

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

    def list_replay_requests(self, *, limit: int = 200) -> tuple[ReplayRequestRecord, ...]:
        safe_limit = max(1, int(limit))
        items = list(self.replay_requests.values())
        items.sort(key=lambda item: item.requested_at, reverse=True)
        return tuple(items[:safe_limit])

    def list_news_items(self, *, symbol: str | None = None, limit: int = 50) -> tuple[NewsPanelItem, ...]:
        symbol_filter = symbol.strip().upper() if symbol else None
        safe_limit = max(1, int(limit))

        items = [
            item
            for item in self.news_items
            if symbol_filter is None or (item.symbol or "").upper() == symbol_filter
        ]
        items.sort(key=lambda item: item.published_at, reverse=True)
        return tuple(items[:safe_limit])

    def list_news_summaries(
        self,
        *,
        symbol_scope: str | None = None,
        limit: int = 20,
    ) -> tuple[NewsPanelSummary, ...]:
        scope_filter = symbol_scope.strip().upper() if symbol_scope else None
        safe_limit = max(1, int(limit))

        items = [
            item
            for item in self.news_summaries
            if scope_filter is None or item.symbol_scope.upper() == scope_filter
        ]
        items.sort(key=lambda item: item.generated_at, reverse=True)
        return tuple(items[:safe_limit])

    def list_news_impact(self, *, limit: int = 10) -> tuple[NewsImpactRecord, ...]:
        safe_limit = max(1, int(limit))
        grouped: dict[str, dict[str, Any]] = {}

        for item in self.news_items:
            symbol = (item.symbol or "GLOBAL").upper()
            row = grouped.setdefault(
                symbol,
                {
                    "headline_count": 0,
                    "sentiment_total": 0.0,
                    "max_relevance": 0.0,
                    "latest_published_at": None,
                    "latest_summary": None,
                },
            )
            row["headline_count"] += 1
            row["sentiment_total"] += float(item.sentiment_score)
            row["max_relevance"] = max(float(row["max_relevance"]), float(item.relevance_score))
            latest = row["latest_published_at"]
            if latest is None or item.published_at > latest:
                row["latest_published_at"] = item.published_at

        for summary in self.news_summaries:
            symbol = summary.symbol_scope.upper()
            row = grouped.setdefault(
                symbol,
                {
                    "headline_count": 0,
                    "sentiment_total": 0.0,
                    "max_relevance": 0.0,
                    "latest_published_at": None,
                    "latest_summary": None,
                },
            )
            if row["latest_summary"] is None:
                row["latest_summary"] = summary.summary_text

        records: list[NewsImpactRecord] = []
        for symbol, row in grouped.items():
            headline_count = int(row["headline_count"])
            avg_sentiment = 0.0 if headline_count == 0 else float(row["sentiment_total"]) / headline_count
            records.append(
                NewsImpactRecord(
                    symbol=symbol,
                    headline_count=headline_count,
                    avg_sentiment=avg_sentiment,
                    max_relevance=float(row["max_relevance"]),
                    latest_published_at=row["latest_published_at"],
                    latest_summary=row["latest_summary"],
                )
            )

        records.sort(key=lambda item: (item.symbol != "GLOBAL", item.headline_count, item.max_relevance), reverse=True)
        return tuple(records[:safe_limit])

    def list_notification_preferences(
        self,
        *,
        user_id: str | None = None,
    ) -> tuple[NotificationPreferenceRecord, ...]:
        if user_id is None:
            items = list(self.notification_preferences.values())
            items.sort(key=lambda item: item.user_id)
            return tuple(items)
        normalized_user_id = _normalize_user_id(user_id)
        record = self.notification_preferences.get(normalized_user_id)
        return (record,) if record is not None else ()

    def upsert_notification_preference(
        self,
        *,
        user_id: str,
        min_severity: str,
        gateways: Sequence[str],
        strategy_ids: Sequence[str],
        event_types: Sequence[str],
        actor: str,
    ) -> NotificationPreferenceRecord:
        normalized_user_id = _normalize_user_id(user_id)
        normalized_actor = actor.strip() or "unknown"
        normalized_severity = _normalize_notification_severity(min_severity)
        normalized_gateways = _normalize_non_empty_values(gateways, lowercase=True)
        if not normalized_gateways:
            raise ValueError("gateways must include at least one value")

        record = NotificationPreferenceRecord(
            user_id=normalized_user_id,
            min_severity=normalized_severity,
            gateways=normalized_gateways,
            strategy_ids=_normalize_non_empty_values(strategy_ids, lowercase=False),
            event_types=_normalize_non_empty_values(event_types, lowercase=False),
            updated_at=_utc_now_iso(),
            updated_by=normalized_actor,
        )
        self.notification_preferences[normalized_user_id] = record
        return record

    def delete_notification_preference(self, *, user_id: str) -> bool:
        normalized_user_id = _normalize_user_id(user_id)
        return self.notification_preferences.pop(normalized_user_id, None) is not None

    def notification_metrics_snapshot(self) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "totals": {
                "received_total": 0,
                "filtered_total": 0,
                "dispatched_total": 0,
                "delivered_total": 0,
                "failed_total": 0,
                "retryable_total": 0,
                "dlq_total": 0,
            },
            "suppression": {"dedupe": 0, "rate_limit": 0},
            "gateway_status": {},
            "retry_attempt_histogram": {},
            "generated_at": _utc_now_iso(),
        }
        merged = {**defaults, **self.notification_metrics}
        merged["totals"] = {**defaults["totals"], **dict(self.notification_metrics.get("totals", {}))}
        merged["suppression"] = {**defaults["suppression"], **dict(self.notification_metrics.get("suppression", {}))}
        merged["gateway_status"] = dict(self.notification_metrics.get("gateway_status", {}))
        merged["retry_attempt_histogram"] = dict(self.notification_metrics.get("retry_attempt_histogram", {}))
        generated_at = str(self.notification_metrics.get("generated_at", "")).strip()
        merged["generated_at"] = generated_at or _utc_now_iso()
        return merged

    def list_notification_delivery_logs(
        self,
        *,
        limit: int = 100,
        gateway: str | None = None,
        status: str | None = None,
        severity: str | None = None,
    ) -> tuple[NotificationDeliveryRecord, ...]:
        safe_limit = max(1, int(limit))
        gateway_filter = gateway.strip().lower() if gateway else None
        status_filter = status.strip().upper() if status else None
        severity_filter = severity.strip().upper() if severity else None

        items: list[NotificationDeliveryRecord] = []
        for item in self.notification_delivery_logs:
            if gateway_filter and item.gateway.strip().lower() != gateway_filter:
                continue
            if status_filter and item.delivery_status.strip().upper() != status_filter:
                continue
            if severity_filter and item.severity.strip().upper() != severity_filter:
                continue
            items.append(item)

        items.sort(key=lambda row: row.logged_at, reverse=True)
        return tuple(items[:safe_limit])

    def list_notification_trace_spans(
        self,
        *,
        limit: int = 100,
        trace_id: str | None = None,
        stage: str | None = None,
    ) -> tuple[NotificationTraceRecord, ...]:
        safe_limit = max(1, int(limit))
        trace_filter = trace_id.strip() if trace_id else None
        stage_filter = stage.strip().lower() if stage else None

        items: list[NotificationTraceRecord] = []
        for item in self.notification_trace_spans:
            if trace_filter and item.trace_id != trace_filter:
                continue
            if stage_filter and item.stage.strip().lower() != stage_filter:
                continue
            items.append(item)

        items.sort(key=lambda row: row.completed_at, reverse=True)
        return tuple(items[:safe_limit])

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

    news_items = [
        NewsPanelItem(
            news_id=str(uuid.uuid4()),
            source="coindesk",
            title="Bitcoin ETF inflows stay positive as volatility compresses",
            url="https://example.com/news/btc-etf-inflows",
            published_at=now,
            symbol="BTC",
            topic="etf",
            relevance_score=0.86,
            sentiment_score=0.42,
        ),
        NewsPanelItem(
            news_id=str(uuid.uuid4()),
            source="theblock",
            title="Ethereum staking demand rises ahead of protocol upgrade",
            url="https://example.com/news/eth-staking-upgrade",
            published_at=now,
            symbol="ETH",
            topic="protocol",
            relevance_score=0.79,
            sentiment_score=0.36,
        ),
    ]
    news_summaries = [
        NewsPanelSummary(
            summary_id=str(uuid.uuid4()),
            symbol_scope="BTC",
            window_start=now,
            window_end=now,
            summary_text="BTC flow remains constructive with sustained ETF demand and stable funding.",
            generated_at=now,
            source_news_ids=(news_items[0].news_id,),
            avg_sentiment=0.42,
        ),
        NewsPanelSummary(
            summary_id=str(uuid.uuid4()),
            symbol_scope="GLOBAL",
            window_start=now,
            window_end=now,
            summary_text="Macro sentiment is neutral-positive with no high-severity security incidents.",
            generated_at=now,
            source_news_ids=(news_items[0].news_id, news_items[1].news_id),
            avg_sentiment=0.39,
        ),
    ]
    notification_preferences = {
        "ops-default": NotificationPreferenceRecord(
            user_id="ops-default",
            min_severity="WARNING",
            gateways=("telegram",),
            strategy_ids=(),
            event_types=(),
            updated_at=now,
            updated_by="system",
        ),
    }
    notification_event_id = str(uuid.uuid4())
    notification_trace_id = str(uuid.uuid4())
    notification_decision_id = str(uuid.uuid4())
    notification_metrics = {
        "totals": {
            "received_total": 8,
            "filtered_total": 2,
            "dispatched_total": 6,
            "delivered_total": 5,
            "failed_total": 1,
            "retryable_total": 2,
            "dlq_total": 1,
        },
        "suppression": {"dedupe": 1, "rate_limit": 1},
        "gateway_status": {"telegram:DELIVERED": 5, "telegram:FAILED": 1},
        "retry_attempt_histogram": {"1": 4, "2": 1, "3": 1},
        "generated_at": now,
    }
    notification_delivery_logs = [
        NotificationDeliveryRecord(
            notification_event_id=notification_event_id,
            trace_id=notification_trace_id,
            decision_id=notification_decision_id,
            event_type="notify.risk.event",
            severity="CRITICAL",
            gateway="telegram",
            delivery_status="DELIVERED",
            attempt=2,
            detail=None,
            logged_at=now,
        )
    ]
    notification_trace_spans = [
        NotificationTraceRecord(
            notification_event_id=notification_event_id,
            trace_id=notification_trace_id,
            decision_id=notification_decision_id,
            stage="policy_router",
            status="routed",
            latency_ms=1.4,
            gateway=None,
            attempt=None,
            started_at=now,
            completed_at=now,
        ),
        NotificationTraceRecord(
            notification_event_id=notification_event_id,
            trace_id=notification_trace_id,
            decision_id=notification_decision_id,
            stage="gateway_dispatch",
            status="succeeded",
            latency_ms=42.0,
            gateway="telegram",
            attempt=2,
            started_at=now,
            completed_at=now,
        ),
    ]

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
        news_items=news_items,
        news_summaries=news_summaries,
        notification_preferences=notification_preferences,
        notification_metrics=notification_metrics,
        notification_delivery_logs=notification_delivery_logs,
        notification_trace_spans=notification_trace_spans,
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


def _normalize_notification_severity(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in _VALID_NOTIFICATION_SEVERITIES:
        raise ValueError("notification severity must be INFO, WARNING, or CRITICAL")
    return normalized


def _normalize_user_id(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("user_id must be non-empty")
    return normalized


def _default_symbol(*, strategy_id: str) -> str:
    lowered = strategy_id.lower()
    if "eth" in lowered:
        return "ETH/USDT"
    return "BTC/USDT"


def _normalize_non_empty_values(values: Sequence[str], *, lowercase: bool) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = str(raw).strip()
        if not text:
            continue
        item = text.lower() if lowercase else text
        if item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return tuple(normalized)


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


def _extract_prompt_preview(prompt_payload: dict[str, Any]) -> str | None:
    messages = prompt_payload.get("messages")
    if not isinstance(messages, list):
        return None
    for item in reversed(messages):
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if content is None:
            continue
        text = str(content).strip()
        if text:
            return _trim_preview(text)
    return None


def _extract_response_preview(response_payload: dict[str, Any]) -> str | None:
    content = response_payload.get("content")
    if content is None:
        return None
    text = str(content).strip()
    if not text:
        return None
    return _trim_preview(text)


def _trim_preview(value: str, *, limit: int = 180) -> str:
    text = value.strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return f"{text[:limit - 3]}..."


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
