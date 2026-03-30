from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserRole(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


class ExecutionMode(str, Enum):
    MOCK = "MOCK"
    REAL = "REAL"


class StrategyRuntimeState(str, Enum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    PAUSED = "PAUSED"


class NotificationSeverityLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AuthPrincipal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    role: UserRole


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    service: str
    time: str


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    service: str
    mode: ExecutionMode
    strategy_count: int
    time: str


class MetadataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_name: str
    app_version: str
    mode: ExecutionMode
    roles_supported: list[UserRole]
    features: list[str]
    generated_at: str


class ModeUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ExecutionMode
    reason: str = Field(min_length=1)


class ModeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ExecutionMode
    updated_at: str
    changed_by: str | None = None
    reason: str | None = None


class ModeAuditRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    mode: ExecutionMode
    changed_by: str
    reason: str
    changed_at: str


class ModeHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ModeAuditRecordResponse]


class StrategyStateUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: StrategyRuntimeState
    reason: str = Field(min_length=1)


class StrategyRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    symbol: str
    mode: ExecutionMode
    state: StrategyRuntimeState
    updated_at: str
    changed_by: str
    reason: str | None = None


class StrategyListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[StrategyRecordResponse]


class OrderRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    symbol: str
    mode: ExecutionMode
    status: str
    requested_quantity: float
    filled_quantity: float
    average_price: float | None = None


class OrderListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OrderRecordResponse]


class PositionRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ExecutionMode
    symbol: str
    quantity: float
    average_entry_price: float
    realized_pnl: float
    status: str
    updated_at: str


class PositionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PositionRecordResponse]


class PortfolioSnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_time: str
    mode: ExecutionMode
    total_balance_usd: float
    available_balance_usd: float
    locked_balance_usd: float
    unrealized_pnl: float
    realized_pnl_total: float


class PortfolioHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PortfolioSnapshotResponse]


class MarketKlineRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time: str
    exchange: str
    symbol: str
    interval: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trades: int


class MarketKlineListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MarketKlineRecordResponse]


class OrderBookLevelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: float
    amount: float


class OrderBookSnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_time: str
    exchange: str
    symbol: str
    best_bid: float
    best_ask: float
    spread_bps: float
    bids: list[OrderBookLevelResponse]
    asks: list[OrderBookLevelResponse]


class TradeRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fill_id: str
    order_id: str
    exchange_fill_id: str
    exchange: str
    symbol: str
    mode: str
    side: str
    quantity: float
    price: float
    fee: float
    fee_currency: str
    filled_at: str


class TradeListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[TradeRecordResponse]


class PipelineStageStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    healthy: bool
    status: str
    records_total: int
    latest_at: str | None = None
    age_seconds: float | None = None
    stale_after_seconds: float
    detail: str | None = None


class PipelineHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: str
    overall_healthy: bool
    mode_filter: str | None = None
    stages: list[PipelineStageStatusResponse]


class LLMRuntimeStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_enabled: bool
    litellm_base_url_configured: bool
    quick_provider_order: list[str]
    deep_provider_order: list[str]
    total_calls: int
    succeeded_calls: int
    failed_calls: int
    latest_call_at: str | None = None


class SignalRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    trace_id: str
    strategy_id: str
    mode: str
    status: str
    action: str
    quantity: float
    confidence: float
    created_at: str


class SignalListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SignalRecordResponse]


class RiskControlEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    control: str
    status: str
    reason: str
    actor: str
    occurred_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kill_switch_enabled: bool
    circuit_breaker_open: bool
    consecutive_failures: int
    circuit_breaker_open_until: str | None
    blocked_by: list[str]
    recent_events: list[RiskControlEventResponse]


class RiskControlCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1)
    cooldown_seconds: int | None = Field(default=None, ge=1)


class RiskControlActionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    control: str
    status: str
    reason: str
    changed_by: str
    occurred_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class NewsItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    news_id: str
    source: str
    title: str
    url: str
    published_at: str
    symbol: str | None
    topic: str
    relevance_score: float
    sentiment_score: float


class NewsItemListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[NewsItemResponse]


class NewsSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_id: str
    symbol_scope: str
    window_start: str
    window_end: str
    summary_text: str
    generated_at: str
    source_count: int
    avg_sentiment: float


class NewsSummaryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[NewsSummaryResponse]


class NewsImpactRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    headline_count: int
    avg_sentiment: float
    max_relevance: float
    latest_published_at: str | None
    latest_summary: str | None


class NewsImpactListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[NewsImpactRecordResponse]


class NotificationPreferenceUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_severity: NotificationSeverityLevel = NotificationSeverityLevel.INFO
    gateways: list[str] = Field(min_length=1)
    strategy_ids: list[str] = Field(default_factory=list)
    event_types: list[str] = Field(default_factory=list)


class NotificationPreferenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    min_severity: NotificationSeverityLevel
    gateways: list[str]
    strategy_ids: list[str]
    event_types: list[str]
    updated_at: str
    updated_by: str


class NotificationPreferenceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[NotificationPreferenceResponse]


class NotificationMetricsTotalsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    received_total: int
    filtered_total: int
    dispatched_total: int
    delivered_total: int
    failed_total: int
    retryable_total: int
    dlq_total: int


class NotificationMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    totals: NotificationMetricsTotalsResponse
    suppression: dict[str, int]
    gateway_status: dict[str, int]
    retry_attempt_histogram: dict[str, int]
    generated_at: str


class NotificationDeliveryRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notification_event_id: str
    trace_id: str
    decision_id: str
    event_type: str
    severity: str
    gateway: str
    delivery_status: str
    attempt: int
    detail: str | None = None
    logged_at: str


class NotificationDeliveryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[NotificationDeliveryRecordResponse]


class NotificationTraceRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notification_event_id: str
    trace_id: str
    decision_id: str
    stage: str
    status: str
    latency_ms: float
    gateway: str | None = None
    attempt: int | None = None
    started_at: str
    completed_at: str


class NotificationTraceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[NotificationTraceRecordResponse]


class LLMUsageRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


class LLMUsageListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[LLMUsageRecordResponse]


class LLMBreachRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_call_id: str
    strategy_id: str
    agent_name: str
    trace_id: str
    decision_id: str
    reason: str
    projected_tokens: int | None
    projected_cost: float | None
    created_at: str


class LLMBreachListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[LLMBreachRecordResponse]


class LLMCallLogRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_call_id: str
    trace_id: str
    decision_id: str
    strategy_id: str
    agent_name: str
    provider: str
    model: str
    status: str
    mode: str | None = None
    tier: str | None = None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    estimated_cost: float
    created_at: str
    prompt_preview: str | None = None
    response_preview: str | None = None


class LLMCallLogListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[LLMCallLogRecordResponse]


class ReplayRequestCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(min_length=1)


class ReplayDecisionResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    trace_id: str
    strategy_id: str
    mode: str
    status: str
    summary: dict[str, Any]
    lifecycle: list[dict[str, Any]]
    agent_runs: list[dict[str, Any]]
    llm_calls: list[dict[str, Any]]
    graph_nodes: list[dict[str, Any]]
    graph_edges: list[dict[str, Any]]
    deterministic_digest: str
    diff: dict[str, Any] | None = None


class ReplayRequestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    decision_id: str
    status: str
    requested_by: str
    requested_at: str
    result: ReplayDecisionResultResponse


class ReplayCatalogDecisionRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    trace_id: str
    strategy_id: str
    mode: str
    status: str
    started_at: str
    completed_at: str


class ReplayCatalogRequestRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    decision_id: str
    status: str
    requested_by: str
    requested_at: str


class ReplayCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[ReplayCatalogDecisionRecordResponse]
    requests: list[ReplayCatalogRequestRecordResponse]
