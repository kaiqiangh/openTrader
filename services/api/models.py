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
    realized_pnl_today: float


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
