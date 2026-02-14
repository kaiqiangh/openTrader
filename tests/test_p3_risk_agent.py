from __future__ import annotations

from services.agent_orchestrator.contracts import PlannerDecision, StrategyConfig
from services.agent_orchestrator.risk_agent import RiskAgent


def _strategy(
    *,
    max_notional: float = 20_000.0,
    max_position: float = 1.0,
    max_drawdown: float = 0.2,
    min_confidence: float = 0.2,
) -> StrategyConfig:
    return StrategyConfig(
        strategy_id="scalp-long-short",
        symbol="BTC/USDT",
        mode="MOCK",
        order_size=0.1,
        planner_buy_threshold=0.2,
        planner_sell_threshold=0.2,
        risk_max_notional_usd=max_notional,
        risk_max_position_size=max_position,
        risk_max_drawdown_pct=max_drawdown,
        risk_min_confidence=min_confidence,
    )


def _plan(*, action: str, qty: float, confidence: float) -> PlannerDecision:
    return PlannerDecision(
        action=action,
        confidence=confidence,
        target_quantity=qty,
        rationale=("signal",),
        metrics={"orderbook_imbalance": confidence},
    )


def test_risk_agent_rejects_plan_when_notional_exceeds_limit() -> None:
    agent = RiskAgent()
    assessment = agent.evaluate(
        plan=_plan(action="BUY", qty=0.08, confidence=0.7),
        market_context={"mid_price": 42_000.0, "current_position": 0.1, "drawdown_pct": 0.01},
        strategy=_strategy(max_notional=2_000.0),
    )

    assert assessment.approved is False
    assert "notional_limit" in assessment.blocked_by
    assert any((signal.name == "notional_limit") and (signal.passed is False) for signal in assessment.signals)


def test_risk_agent_rejects_low_confidence_plan() -> None:
    agent = RiskAgent()
    assessment = agent.evaluate(
        plan=_plan(action="BUY", qty=0.02, confidence=0.05),
        market_context={"mid_price": 42_000.0, "current_position": 0.1, "drawdown_pct": 0.01},
        strategy=_strategy(min_confidence=0.2),
    )

    assert assessment.approved is False
    assert "confidence_minimum" in assessment.blocked_by


def test_risk_agent_approves_plan_within_limits() -> None:
    agent = RiskAgent()
    plan = _plan(action="SELL", qty=-0.02, confidence=0.65)
    assessment = agent.evaluate(
        plan=plan,
        market_context={"mid_price": 42_000.0, "current_position": 0.15, "drawdown_pct": 0.01},
        strategy=_strategy(max_notional=20_000.0, max_position=1.0),
    )

    assert assessment.approved is True
    assert assessment.blocked_by == ()
    assert assessment.approved_quantity == plan.target_quantity
