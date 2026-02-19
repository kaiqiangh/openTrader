from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import json

from services.agent_orchestrator.contracts import (
    ExecutionDecision,
    PlannerDecision,
    RiskAssessment,
    StrategyConfig,
)
from services.llm_gateway.contracts import LLMRequest
from services.llm_gateway.gateway import LLMGateway


@dataclass(frozen=True, slots=True)
class PlannerSuggestion:
    action: str | None
    confidence: float | None
    target_quantity: float | None
    rationale: tuple[str, ...]
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RiskSuggestion:
    approved: bool | None
    approved_quantity: float | None
    risk_score: float | None
    blocked_by: tuple[str, ...]
    rationale: tuple[str, ...]
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ExecutionSuggestion:
    action: str | None
    quantity: float | None
    confidence: float | None
    constraints: dict[str, Any]
    rationale: tuple[str, ...]
    metadata: dict[str, Any]


class LLMDecisionRuntime:
    """Gateway-backed runtime for planner/risk/execution LLM suggestions."""

    def __init__(
        self,
        *,
        gateway: LLMGateway,
        quick_provider_order: tuple[str, ...],
        deep_provider_order: tuple[str, ...],
        quick_temperature: float = 0.1,
        deep_temperature: float = 0.2,
    ) -> None:
        self.gateway = gateway
        self.quick_provider_order = tuple(alias.strip() for alias in quick_provider_order if alias.strip())
        self.deep_provider_order = tuple(alias.strip() for alias in deep_provider_order if alias.strip())
        self.quick_temperature = float(quick_temperature)
        self.deep_temperature = float(deep_temperature)

    async def suggest_plan(
        self,
        *,
        trace_id: str,
        decision_id: str,
        market_context: Mapping[str, Any],
        strategy: StrategyConfig,
        heuristic_plan: PlannerDecision,
    ) -> PlannerSuggestion:
        response = await self.gateway.generate(
            LLMRequest(
                trace_id=trace_id,
                decision_id=decision_id,
                strategy_id=strategy.strategy_id,
                agent_name="planner",
                messages=_planner_messages(
                    market_context=market_context,
                    strategy=strategy,
                    heuristic_plan=heuristic_plan,
                ),
                temperature=self.quick_temperature,
                max_tokens=350,
                metadata={"tier": "quick", "symbol": strategy.symbol, "mode": strategy.mode},
            ),
            provider_order=self.quick_provider_order,
        )
        payload = _parse_response_payload(response.content)
        return PlannerSuggestion(
            action=_optional_upper(payload.get("action")),
            confidence=_optional_float(payload.get("confidence")),
            target_quantity=_optional_float(payload.get("target_quantity")),
            rationale=_normalize_rationale(payload.get("rationale")),
            metadata={"provider": response.provider, "model": response.model, "tier": "quick"},
        )

    async def suggest_risk(
        self,
        *,
        trace_id: str,
        decision_id: str,
        market_context: Mapping[str, Any],
        strategy: StrategyConfig,
        heuristic_risk: RiskAssessment,
        heuristic_plan: PlannerDecision,
    ) -> RiskSuggestion:
        response = await self.gateway.generate(
            LLMRequest(
                trace_id=trace_id,
                decision_id=decision_id,
                strategy_id=strategy.strategy_id,
                agent_name="risk",
                messages=_risk_messages(
                    market_context=market_context,
                    strategy=strategy,
                    heuristic_risk=heuristic_risk,
                    heuristic_plan=heuristic_plan,
                ),
                temperature=self.quick_temperature,
                max_tokens=350,
                metadata={"tier": "quick", "symbol": strategy.symbol, "mode": strategy.mode},
            ),
            provider_order=self.quick_provider_order,
        )
        payload = _parse_response_payload(response.content)
        return RiskSuggestion(
            approved=_optional_bool(payload.get("approved")),
            approved_quantity=_optional_float(payload.get("approved_quantity")),
            risk_score=_optional_float(payload.get("risk_score")),
            blocked_by=_normalize_tokens(payload.get("blocked_by")),
            rationale=_normalize_rationale(payload.get("rationale")),
            metadata={"provider": response.provider, "model": response.model, "tier": "quick"},
        )

    async def suggest_execution(
        self,
        *,
        trace_id: str,
        decision_id: str,
        market_context: Mapping[str, Any],
        strategy: StrategyConfig,
        heuristic_execution: ExecutionDecision,
        heuristic_plan: PlannerDecision,
        heuristic_risk: RiskAssessment,
    ) -> ExecutionSuggestion:
        response = await self.gateway.generate(
            LLMRequest(
                trace_id=trace_id,
                decision_id=decision_id,
                strategy_id=strategy.strategy_id,
                agent_name="execution_decision",
                messages=_execution_messages(
                    market_context=market_context,
                    strategy=strategy,
                    heuristic_execution=heuristic_execution,
                    heuristic_plan=heuristic_plan,
                    heuristic_risk=heuristic_risk,
                ),
                temperature=self.deep_temperature,
                max_tokens=450,
                metadata={"tier": "deep", "symbol": strategy.symbol, "mode": strategy.mode},
            ),
            provider_order=self.deep_provider_order,
        )
        payload = _parse_response_payload(response.content)
        constraints = payload.get("constraints")
        normalized_constraints = dict(constraints) if isinstance(constraints, Mapping) else {}
        return ExecutionSuggestion(
            action=_optional_upper(payload.get("action")),
            quantity=_optional_float(payload.get("quantity")),
            confidence=_optional_float(payload.get("confidence")),
            constraints=normalized_constraints,
            rationale=_normalize_rationale(payload.get("rationale")),
            metadata={"provider": response.provider, "model": response.model, "tier": "deep"},
        )


def _planner_messages(
    *,
    market_context: Mapping[str, Any],
    strategy: StrategyConfig,
    heuristic_plan: PlannerDecision,
) -> tuple[dict[str, Any], ...]:
    return (
        {
            "role": "system",
            "content": (
                "You are the planner agent for a crypto spot strategy. Return JSON only with keys: "
                "action (BUY/SELL/HOLD/CLOSE), confidence (0..1), target_quantity, rationale (array)."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "strategy": {
                        "strategy_id": strategy.strategy_id,
                        "symbol": strategy.symbol,
                        "mode": strategy.mode,
                        "order_size": strategy.order_size,
                        "buy_threshold": strategy.planner_buy_threshold,
                        "sell_threshold": strategy.planner_sell_threshold,
                    },
                    "market_context": dict(market_context),
                    "heuristic_plan": {
                        "action": heuristic_plan.action,
                        "confidence": heuristic_plan.confidence,
                        "target_quantity": heuristic_plan.target_quantity,
                        "rationale": list(heuristic_plan.rationale),
                    },
                },
                ensure_ascii=True,
            ),
        },
    )


def _risk_messages(
    *,
    market_context: Mapping[str, Any],
    strategy: StrategyConfig,
    heuristic_risk: RiskAssessment,
    heuristic_plan: PlannerDecision,
) -> tuple[dict[str, Any], ...]:
    return (
        {
            "role": "system",
            "content": (
                "You are the risk agent. Return JSON only with keys: approved (bool), approved_quantity, "
                "risk_score (0..1), blocked_by (array), rationale (array)."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "strategy": {
                        "strategy_id": strategy.strategy_id,
                        "symbol": strategy.symbol,
                        "mode": strategy.mode,
                        "risk_max_notional_usd": strategy.risk_max_notional_usd,
                        "risk_max_position_size": strategy.risk_max_position_size,
                        "risk_max_drawdown_pct": strategy.risk_max_drawdown_pct,
                        "risk_min_confidence": strategy.risk_min_confidence,
                    },
                    "market_context": dict(market_context),
                    "heuristic_plan": {
                        "action": heuristic_plan.action,
                        "confidence": heuristic_plan.confidence,
                        "target_quantity": heuristic_plan.target_quantity,
                    },
                    "heuristic_risk": {
                        "approved": heuristic_risk.approved,
                        "approved_quantity": heuristic_risk.approved_quantity,
                        "risk_score": heuristic_risk.risk_score,
                        "blocked_by": list(heuristic_risk.blocked_by),
                    },
                },
                ensure_ascii=True,
            ),
        },
    )


def _execution_messages(
    *,
    market_context: Mapping[str, Any],
    strategy: StrategyConfig,
    heuristic_execution: ExecutionDecision,
    heuristic_plan: PlannerDecision,
    heuristic_risk: RiskAssessment,
) -> tuple[dict[str, Any], ...]:
    return (
        {
            "role": "system",
            "content": (
                "You are the execution decision agent. Return JSON only with keys: action (BUY/SELL/HOLD/CLOSE), "
                "quantity, confidence (0..1), constraints (object), rationale (array)."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "strategy": {
                        "strategy_id": strategy.strategy_id,
                        "symbol": strategy.symbol,
                        "mode": strategy.mode,
                        "allowed_actions": list(strategy.allowed_actions),
                    },
                    "market_context": dict(market_context),
                    "heuristic_plan": {
                        "action": heuristic_plan.action,
                        "confidence": heuristic_plan.confidence,
                        "target_quantity": heuristic_plan.target_quantity,
                    },
                    "heuristic_risk": {
                        "approved": heuristic_risk.approved,
                        "approved_quantity": heuristic_risk.approved_quantity,
                        "risk_score": heuristic_risk.risk_score,
                        "blocked_by": list(heuristic_risk.blocked_by),
                    },
                    "heuristic_execution": {
                        "action": heuristic_execution.action,
                        "quantity": heuristic_execution.quantity,
                        "confidence": heuristic_execution.confidence,
                        "constraints": dict(heuristic_execution.constraints),
                    },
                },
                ensure_ascii=True,
            ),
        },
    )


def _parse_response_payload(content: str) -> dict[str, Any]:
    value = content.strip()
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, Mapping):
        return dict(parsed)
    return {}


def _optional_upper(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    return normalized


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    return None


def _normalize_tokens(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    output: list[str] = []
    for item in value:
        text = str(item).strip()
        if not text:
            continue
        output.append(text)
    return tuple(output)


def _normalize_rationale(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    output: list[str] = []
    for item in value:
        text = str(item).strip()
        if not text:
            continue
        output.append(text)
    return tuple(output)
