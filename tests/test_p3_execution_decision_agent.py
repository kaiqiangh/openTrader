from __future__ import annotations

from services.agent_orchestrator.contracts import (
    PlannerDecision,
    RiskAssessment,
    RiskSignal,
    StrategyConfig,
)
from services.agent_orchestrator.execution_decision_agent import ExecutionDecisionAgent


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
    )


def _plan(*, action: str, quantity: float, confidence: float) -> PlannerDecision:
    return PlannerDecision(
        action=action,  # type: ignore[arg-type]
        confidence=confidence,
        target_quantity=quantity,
        rationale=("planner-output",),
        metrics={"orderbook_imbalance": confidence},
    )


def _risk(
    *, approved: bool, approved_quantity: float, blocked_by: tuple[str, ...]
) -> RiskAssessment:
    signals = (
        RiskSignal(
            name="confidence_minimum",
            passed=approved,
            value=0.8 if approved else 0.1,
            limit=0.2,
            message="confidence gate",
        ),
    )
    return RiskAssessment(
        approved=approved,
        approved_quantity=approved_quantity,
        signals=signals,
        blocked_by=blocked_by,
        risk_score=0.0 if approved else 1.0,
        rationale=("risk-output",),
    )


def test_execution_decision_proposes_buy_with_positive_quantity() -> None:
    agent = ExecutionDecisionAgent()
    proposal = agent.propose_action(
        plan=_plan(action="BUY", quantity=0.04, confidence=0.72),
        risk=_risk(approved=True, approved_quantity=0.04, blocked_by=()),
        market_context={"current_position": 0.1, "mid_price": 42_000.0},
        strategy=_strategy(),
    )

    assert proposal.action == "BUY"
    assert proposal.quantity > 0
    assert proposal.constraints["schema_valid"] is True


def test_execution_decision_proposes_sell_with_negative_quantity() -> None:
    agent = ExecutionDecisionAgent()
    proposal = agent.propose_action(
        plan=_plan(action="SELL", quantity=-0.03, confidence=0.67),
        risk=_risk(approved=True, approved_quantity=-0.03, blocked_by=()),
        market_context={"current_position": 0.2, "mid_price": 42_000.0},
        strategy=_strategy(),
    )

    assert proposal.action == "SELL"
    assert proposal.quantity < 0


def test_execution_decision_proposes_hold_when_risk_not_approved() -> None:
    agent = ExecutionDecisionAgent()
    proposal = agent.propose_action(
        plan=_plan(action="BUY", quantity=0.05, confidence=0.75),
        risk=_risk(approved=False, approved_quantity=0.0, blocked_by=("notional_limit",)),
        market_context={"current_position": 0.1, "mid_price": 42_000.0},
        strategy=_strategy(),
    )

    assert proposal.action == "HOLD"
    assert proposal.quantity == 0.0
    assert "notional_limit" in " ".join(proposal.rationale)


def test_execution_decision_close_flattens_open_position() -> None:
    agent = ExecutionDecisionAgent()
    proposal = agent.propose_action(
        plan=_plan(action="CLOSE", quantity=0.0, confidence=0.65),
        risk=_risk(approved=True, approved_quantity=0.0, blocked_by=()),
        market_context={"current_position": 0.25, "mid_price": 42_000.0},
        strategy=_strategy(),
    )

    assert proposal.action == "CLOSE"
    assert proposal.quantity == -0.25
