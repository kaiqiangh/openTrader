from __future__ import annotations

from typing import Any, Mapping

from services.agent_orchestrator.contracts import PlannerDecision, RiskAssessment, RiskSignal, StrategyConfig


class RiskAgent:
    def evaluate(
        self,
        *,
        plan: PlannerDecision,
        market_context: Mapping[str, Any],
        strategy: StrategyConfig,
    ) -> RiskAssessment:
        mid_price = float(market_context.get("mid_price", 0.0))
        current_position = abs(float(market_context.get("current_position", 0.0)))
        drawdown_pct = float(market_context.get("drawdown_pct", 0.0))
        proposed_quantity = abs(plan.target_quantity)
        proposed_notional = proposed_quantity * mid_price
        projected_position = current_position + proposed_quantity

        signals = (
            RiskSignal(
                name="confidence_minimum",
                passed=plan.confidence >= strategy.risk_min_confidence,
                value=plan.confidence,
                limit=strategy.risk_min_confidence,
                message="Planner confidence must meet minimum threshold",
            ),
            RiskSignal(
                name="actionable_plan",
                passed=(plan.action in {"BUY", "SELL", "CLOSE"}) and proposed_quantity > 0,
                value=1.0 if proposed_quantity > 0 else 0.0,
                limit=1.0,
                message="Plan action must produce a non-zero executable quantity",
            ),
            RiskSignal(
                name="notional_limit",
                passed=proposed_notional <= strategy.risk_max_notional_usd,
                value=proposed_notional,
                limit=strategy.risk_max_notional_usd,
                message="Planned notional must remain within max_notional_usd",
            ),
            RiskSignal(
                name="position_limit",
                passed=projected_position <= strategy.risk_max_position_size,
                value=projected_position,
                limit=strategy.risk_max_position_size,
                message="Projected position must remain within max_position_size",
            ),
            RiskSignal(
                name="drawdown_limit",
                passed=drawdown_pct <= strategy.risk_max_drawdown_pct,
                value=drawdown_pct,
                limit=strategy.risk_max_drawdown_pct,
                message="Current drawdown must remain within risk threshold",
            ),
        )

        blocked_by = tuple(signal.name for signal in signals if not signal.passed)
        approved = len(blocked_by) == 0
        risk_score = len(blocked_by) / len(signals)
        approved_quantity = plan.target_quantity if approved else 0.0

        rationale = (
            f"proposed_notional={proposed_notional:.2f}",
            f"projected_position={projected_position:.6f}",
            f"drawdown_pct={drawdown_pct:.4f}",
        )

        return RiskAssessment(
            approved=approved,
            approved_quantity=approved_quantity,
            signals=signals,
            blocked_by=blocked_by,
            risk_score=risk_score,
            rationale=rationale,
        )
