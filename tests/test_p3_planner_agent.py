from __future__ import annotations

from services.agent_orchestrator.contracts import StrategyConfig
from services.agent_orchestrator.planner_agent import PlannerAgent


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


def test_planner_generates_buy_plan_for_positive_orderbook_imbalance() -> None:
    planner = PlannerAgent()
    decision = planner.build_plan(
        market_context={"best_bid_size": 4.0, "best_ask_size": 1.0, "mid_price": 42_000.0},
        strategy=_strategy(),
    )

    assert decision.action == "BUY"
    assert decision.target_quantity > 0
    assert decision.metrics["orderbook_imbalance"] > 0
    assert any("imbalance" in reason for reason in decision.rationale)


def test_planner_generates_sell_plan_for_negative_orderbook_imbalance() -> None:
    planner = PlannerAgent()
    decision = planner.build_plan(
        market_context={"best_bid_size": 1.0, "best_ask_size": 3.5, "mid_price": 42_000.0},
        strategy=_strategy(),
    )

    assert decision.action == "SELL"
    assert decision.target_quantity < 0
    assert decision.metrics["orderbook_imbalance"] < 0


def test_planner_holds_when_imbalance_within_threshold() -> None:
    planner = PlannerAgent()
    decision = planner.build_plan(
        market_context={"best_bid_size": 1.1, "best_ask_size": 1.0, "mid_price": 42_000.0},
        strategy=_strategy(),
    )

    assert decision.action == "HOLD"
    assert decision.target_quantity == 0.0
