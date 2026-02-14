from __future__ import annotations

from typing import Any, Mapping

from services.agent_orchestrator.contracts import PlannerDecision, StrategyConfig


class PlannerAgent:
    def build_plan(
        self,
        *,
        market_context: Mapping[str, Any],
        strategy: StrategyConfig,
    ) -> PlannerDecision:
        bid_size = max(0.0, float(market_context.get("best_bid_size", 0.0)))
        ask_size = max(0.0, float(market_context.get("best_ask_size", 0.0)))
        total_size = bid_size + ask_size
        imbalance = 0.0
        if total_size > 0:
            imbalance = (bid_size - ask_size) / total_size

        action = self._select_action(imbalance=imbalance, strategy=strategy)
        confidence = min(1.0, abs(imbalance))

        if action == "HOLD":
            target_quantity = 0.0
        else:
            scaled_quantity = strategy.order_size * max(confidence, strategy.risk_min_confidence)
            target_quantity = scaled_quantity if action == "BUY" else -scaled_quantity

        rationale = (
            f"orderbook imbalance={imbalance:.4f}",
            f"buy_threshold={strategy.planner_buy_threshold:.4f}",
            f"sell_threshold={strategy.planner_sell_threshold:.4f}",
        )

        metrics = {
            "orderbook_imbalance": imbalance,
            "mid_price": float(market_context.get("mid_price", 0.0)),
            "best_bid_size": bid_size,
            "best_ask_size": ask_size,
        }
        return PlannerDecision(
            action=action,
            confidence=confidence,
            target_quantity=target_quantity,
            rationale=rationale,
            metrics=metrics,
        )

    @staticmethod
    def _select_action(*, imbalance: float, strategy: StrategyConfig) -> str:
        if imbalance >= strategy.planner_buy_threshold:
            return "BUY"
        if imbalance <= -strategy.planner_sell_threshold:
            return "SELL"
        return "HOLD"
