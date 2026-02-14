from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

DecisionAction = Literal["BUY", "SELL", "HOLD", "CLOSE"]


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    strategy_id: str
    symbol: str
    mode: str
    order_size: float
    planner_buy_threshold: float
    planner_sell_threshold: float
    risk_max_notional_usd: float
    risk_max_position_size: float
    risk_max_drawdown_pct: float
    risk_min_confidence: float
    max_leverage: float = 3.0
    allowed_actions: tuple[str, ...] = ("BUY", "SELL", "HOLD", "CLOSE")


@dataclass(frozen=True, slots=True)
class PlannerDecision:
    action: DecisionAction
    confidence: float
    target_quantity: float
    rationale: tuple[str, ...]
    metrics: dict[str, float]


@dataclass(frozen=True, slots=True)
class RiskSignal:
    name: str
    passed: bool
    value: float
    limit: float
    message: str


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    approved: bool
    approved_quantity: float
    signals: tuple[RiskSignal, ...]
    blocked_by: tuple[str, ...]
    risk_score: float
    rationale: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExecutionDecision:
    action: DecisionAction
    quantity: float
    confidence: float
    rationale: tuple[str, ...]
    constraints: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GuardrailViolation:
    code: str
    message: str
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GuardrailValidationResult:
    allowed: bool
    blocked_by: tuple[str, ...]
    violations: tuple[GuardrailViolation, ...]
    checks: dict[str, bool]


@dataclass(frozen=True, slots=True)
class MarketContextOutput:
    context: dict[str, Any]
    microstructure: dict[str, Any]
    news: dict[str, Any]
    quality: dict[str, Any]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    trace_id: str
    decision_id: str
    mode: str
    status: str
    lifecycle: tuple[dict[str, Any], ...]
    market_context: MarketContextOutput
    plan: PlannerDecision
    risk: RiskAssessment
    execution_decision: ExecutionDecision
    guardrail: GuardrailValidationResult
    execution_intent: dict[str, Any] | None
