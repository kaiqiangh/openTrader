from __future__ import annotations

from services.agent_orchestrator.contracts import (
    ExecutionDecision,
    PlannerDecision,
    RiskAssessment,
    RiskSignal,
    StrategyConfig,
)
from services.agent_orchestrator.guardrail_validation import GuardrailValidationLayer


def _strategy() -> StrategyConfig:
    return StrategyConfig(
        strategy_id="scalp-long-short",
        symbol="BTC/USDT",
        mode="MOCK",
        order_size=0.1,
        planner_buy_threshold=0.2,
        planner_sell_threshold=0.2,
        risk_max_notional_usd=20_000.0,
        risk_max_position_size=1.0,
        risk_max_drawdown_pct=0.2,
        risk_min_confidence=0.2,
        max_leverage=2.0,
    )


def _plan(action: str = "BUY", confidence: float = 0.6, qty: float = 0.05) -> PlannerDecision:
    return PlannerDecision(
        action=action,  # type: ignore[arg-type]
        confidence=confidence,
        target_quantity=qty,
        rationale=("planner",),
        metrics={"orderbook_imbalance": confidence},
    )


def _risk(approved: bool = True) -> RiskAssessment:
    return RiskAssessment(
        approved=approved,
        approved_quantity=0.05 if approved else 0.0,
        signals=(
            RiskSignal(
                name="notional_limit",
                passed=approved,
                value=1000.0,
                limit=20_000.0,
                message="ok",
            ),
        ),
        blocked_by=() if approved else ("notional_limit",),
        risk_score=0.0 if approved else 1.0,
        rationale=("risk",),
    )


def _decision(action: str = "BUY", quantity: float = 0.05, confidence: float = 0.6) -> ExecutionDecision:
    return ExecutionDecision(
        action=action,  # type: ignore[arg-type]
        quantity=quantity,
        confidence=confidence,
        rationale=("execution",),
        constraints={"schema_valid": True},
    )


def _market_context(symbol: str = "BTC/USDT", mid_price: float = 42_000.0) -> dict[str, float | str]:
    return {
        "symbol": symbol,
        "mid_price": mid_price,
        "current_position": 0.1,
        "equity_usd": 10_000.0,
    }


def test_guardrail_allows_valid_decision() -> None:
    layer = GuardrailValidationLayer()
    result = layer.validate(
        strategy=_strategy(),
        market_context=_market_context(),
        plan=_plan(),
        risk=_risk(),
        decision=_decision(),
    )

    assert result.allowed is True
    assert result.blocked_by == ()


def test_guardrail_rejects_symbol_mismatch() -> None:
    layer = GuardrailValidationLayer()
    result = layer.validate(
        strategy=_strategy(),
        market_context=_market_context(symbol="ETH/USDT"),
        plan=_plan(),
        risk=_risk(),
        decision=_decision(),
    )

    assert result.allowed is False
    assert "symbol_constraint" in result.blocked_by


def test_guardrail_rejects_low_confidence_executable_action() -> None:
    layer = GuardrailValidationLayer()
    result = layer.validate(
        strategy=_strategy(),
        market_context=_market_context(),
        plan=_plan(confidence=0.1),
        risk=_risk(),
        decision=_decision(confidence=0.1),
    )

    assert result.allowed is False
    assert "confidence_threshold" in result.blocked_by


def test_guardrail_rejects_executable_action_when_risk_not_approved() -> None:
    layer = GuardrailValidationLayer()
    result = layer.validate(
        strategy=_strategy(),
        market_context=_market_context(),
        plan=_plan(),
        risk=_risk(approved=False),
        decision=_decision(action="BUY", quantity=0.05),
    )

    assert result.allowed is False
    assert "risk_alignment" in result.blocked_by


def test_guardrail_rejects_leverage_breach() -> None:
    layer = GuardrailValidationLayer()
    result = layer.validate(
        strategy=_strategy(),
        market_context={"symbol": "BTC/USDT", "mid_price": 42_000.0, "current_position": 0.1, "equity_usd": 500},
        plan=_plan(),
        risk=_risk(),
        decision=_decision(action="BUY", quantity=0.5),
    )

    assert result.allowed is False
    assert "leverage_limit" in result.blocked_by
