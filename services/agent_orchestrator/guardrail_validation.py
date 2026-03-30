from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from services.agent_orchestrator.contracts import (
    ExecutionDecision,
    GuardrailValidationResult,
    GuardrailViolation,
    PlannerDecision,
    RiskAssessment,
    StrategyConfig,
)


class GuardrailValidationLayer:
    def validate(
        self,
        *,
        strategy: StrategyConfig,
        market_context: Mapping[str, Any],
        plan: PlannerDecision,
        risk: RiskAssessment,
        decision: ExecutionDecision,
    ) -> GuardrailValidationResult:
        checks: dict[str, bool] = {}
        violations: list[GuardrailViolation] = []

        symbol = str(market_context.get("symbol", ""))
        action = str(decision.action).upper()
        quantity = Decimal(str(decision.quantity))
        confidence = Decimal(str(decision.confidence))
        mid_price = Decimal(str(max(market_context.get("mid_price", 0.0), 0.0)))
        current_position = Decimal(str(market_context.get("current_position", 0.0)))
        projected_position = current_position + quantity
        projected_notional = abs(quantity) * mid_price
        equity_usd = Decimal(str(max(market_context.get("equity_usd", float(mid_price) if mid_price > 0 else 1.0), 1.0)))
        projected_leverage = abs(projected_position * mid_price) / equity_usd if mid_price > 0 else Decimal("0")

        checks["action_allowed"] = action in set(strategy.allowed_actions)
        if not checks["action_allowed"]:
            violations.append(
                GuardrailViolation(
                    code="action_schema",
                    message="action not in allowed action set",
                    details={"action": action, "allowed_actions": list(strategy.allowed_actions)},
                )
            )

        checks["quantity_semantics"] = self._quantity_semantics_valid(action=action, quantity=quantity)
        if not checks["quantity_semantics"]:
            violations.append(
                GuardrailViolation(
                    code="quantity_semantics",
                    message="quantity sign does not match action semantics",
                    details={"action": action, "quantity": quantity},
                )
            )

        checks["symbol_constraint"] = symbol == strategy.symbol
        if not checks["symbol_constraint"]:
            violations.append(
                GuardrailViolation(
                    code="symbol_constraint",
                    message="market symbol does not match strategy symbol",
                    details={"market_symbol": symbol, "strategy_symbol": strategy.symbol},
                )
            )

        executable_action = action in {"BUY", "SELL", "CLOSE"}

        checks["confidence_threshold"] = (not executable_action) or (
            confidence >= Decimal(str(strategy.risk_min_confidence))
        )
        if not checks["confidence_threshold"]:
            violations.append(
                GuardrailViolation(
                    code="confidence_threshold",
                    message="decision confidence below required threshold",
                    details={
                        "confidence": confidence,
                        "minimum": strategy.risk_min_confidence,
                    },
                )
            )

        checks["risk_alignment"] = (not executable_action) or risk.approved
        if not checks["risk_alignment"]:
            violations.append(
                GuardrailViolation(
                    code="risk_alignment",
                    message="executable action requires approved risk assessment",
                    details={"risk_approved": risk.approved, "blocked_by": list(risk.blocked_by)},
                )
            )

        checks["notional_limit"] = (not executable_action) or (
            projected_notional <= Decimal(str(strategy.risk_max_notional_usd))
        )
        if not checks["notional_limit"]:
            violations.append(
                GuardrailViolation(
                    code="notional_limit",
                    message="projected notional exceeds strategy notional limit",
                    details={
                        "projected_notional": projected_notional,
                        "max_notional": strategy.risk_max_notional_usd,
                    },
                )
            )

        checks["position_limit"] = (not executable_action) or (
            abs(projected_position) <= Decimal(str(strategy.risk_max_position_size))
        )
        if not checks["position_limit"]:
            violations.append(
                GuardrailViolation(
                    code="position_limit",
                    message="projected position exceeds strategy max position size",
                    details={
                        "projected_position": projected_position,
                        "max_position_size": strategy.risk_max_position_size,
                    },
                )
            )

        checks["leverage_limit"] = (not executable_action) or (
            projected_leverage <= Decimal(str(strategy.max_leverage))
        )
        if not checks["leverage_limit"]:
            violations.append(
                GuardrailViolation(
                    code="leverage_limit",
                    message="projected leverage exceeds configured max leverage",
                    details={
                        "projected_leverage": projected_leverage,
                        "max_leverage": strategy.max_leverage,
                    },
                )
            )

        allowed = len(violations) == 0
        blocked_by = tuple(item.code for item in violations)
        return GuardrailValidationResult(
            allowed=allowed,
            blocked_by=blocked_by,
            violations=tuple(violations),
            checks=checks,
        )

    @staticmethod
    def _quantity_semantics_valid(*, action: str, quantity: Decimal) -> bool:
        if action == "BUY":
            return quantity > Decimal("0")
        if action == "SELL":
            return quantity < Decimal("0")
        if action == "CLOSE":
            return quantity != Decimal("0")
        if action == "HOLD":
            return quantity == Decimal("0")
        return False

