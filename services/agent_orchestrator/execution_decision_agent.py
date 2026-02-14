from __future__ import annotations

from typing import Any, Mapping

from services.agent_orchestrator.contracts import (
    ExecutionDecision,
    PlannerDecision,
    RiskAssessment,
    StrategyConfig,
)


ALLOWED_ACTIONS = ("BUY", "SELL", "HOLD", "CLOSE")


class ExecutionDecisionAgent:
    def propose_action(
        self,
        *,
        plan: PlannerDecision,
        risk: RiskAssessment,
        market_context: Mapping[str, Any],
        strategy: StrategyConfig,
    ) -> ExecutionDecision:
        if not risk.approved:
            rationale = (
                "risk_not_approved",
                f"blocked_by={','.join(risk.blocked_by)}",
            )
            return ExecutionDecision(
                action="HOLD",
                quantity=0.0,
                confidence=self._clamp_confidence(plan.confidence),
                rationale=rationale,
                constraints=self._constraints(
                    action="HOLD",
                    quantity=0.0,
                    risk=risk,
                    strategy=strategy,
                ),
            )

        action = self._normalize_action(plan.action)
        quantity = self._resolve_quantity(
            action=action,
            plan=plan,
            risk=risk,
            current_position=float(market_context.get("current_position", 0.0)),
            default_size=strategy.order_size,
        )
        action, quantity = self._normalize_action_quantity(action=action, quantity=quantity)

        rationale = (
            f"planner_action={plan.action}",
            f"risk_approved_quantity={risk.approved_quantity:.8f}",
            f"final_action={action}",
            f"final_quantity={quantity:.8f}",
        )
        return ExecutionDecision(
            action=action,
            quantity=quantity,
            confidence=self._clamp_confidence(plan.confidence),
            rationale=rationale,
            constraints=self._constraints(
                action=action,
                quantity=quantity,
                risk=risk,
                strategy=strategy,
            ),
        )

    @staticmethod
    def _normalize_action(action: str) -> str:
        normalized = str(action).upper()
        if normalized in ALLOWED_ACTIONS:
            return normalized
        return "HOLD"

    @staticmethod
    def _resolve_quantity(
        *,
        action: str,
        plan: PlannerDecision,
        risk: RiskAssessment,
        current_position: float,
        default_size: float,
    ) -> float:
        if action == "HOLD":
            return 0.0

        if action == "CLOSE":
            if current_position == 0.0:
                return 0.0
            return -current_position

        base_quantity = risk.approved_quantity
        if base_quantity == 0.0:
            base_quantity = plan.target_quantity if plan.target_quantity != 0.0 else default_size

        if action == "BUY":
            return abs(base_quantity)
        if action == "SELL":
            return -abs(base_quantity)
        return 0.0

    @staticmethod
    def _normalize_action_quantity(*, action: str, quantity: float) -> tuple[str, float]:
        if action == "BUY" and quantity <= 0.0:
            return "HOLD", 0.0
        if action == "SELL" and quantity >= 0.0:
            return "HOLD", 0.0
        if action == "CLOSE" and quantity == 0.0:
            return "HOLD", 0.0
        if action == "HOLD":
            return "HOLD", 0.0
        return action, quantity

    @staticmethod
    def _clamp_confidence(confidence: float) -> float:
        return max(0.0, min(1.0, float(confidence)))

    @staticmethod
    def _constraints(
        *,
        action: str,
        quantity: float,
        risk: RiskAssessment,
        strategy: StrategyConfig,
    ) -> dict[str, Any]:
        schema_valid = action in ALLOWED_ACTIONS
        if action == "BUY":
            schema_valid = schema_valid and quantity > 0.0
        elif action == "SELL":
            schema_valid = schema_valid and quantity < 0.0
        elif action == "CLOSE":
            schema_valid = schema_valid and quantity != 0.0
        elif action == "HOLD":
            schema_valid = schema_valid and quantity == 0.0

        return {
            "schema_valid": schema_valid,
            "allowed_actions": list(ALLOWED_ACTIONS),
            "risk_approved": risk.approved,
            "blocked_by": list(risk.blocked_by),
            "mode": strategy.mode,
        }
