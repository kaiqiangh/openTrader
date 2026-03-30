"""Extended tests for services/agent_orchestrator/ — guardrail, risk, execution decision.

TEST-002: Adds coverage for edge cases beyond existing p3_* tests.
"""

from __future__ import annotations

from services.agent_orchestrator.contracts import (
    ExecutionDecision,
    PlannerDecision,
    RiskAssessment,
    RiskSignal,
    StrategyConfig,
)
from services.agent_orchestrator.execution_decision_agent import (
    ExecutionDecisionAgent,
    ALLOWED_ACTIONS,
)
from services.agent_orchestrator.guardrail_validation import GuardrailValidationLayer
from services.agent_orchestrator.risk_agent import RiskAgent


# ═══════════════════════════════════════════════════════════════════════════════
# Shared factories
# ═══════════════════════════════════════════════════════════════════════════════


def _strategy(**overrides) -> StrategyConfig:
    defaults = dict(
        strategy_id="test-strategy",
        symbol="BTC/USDT",
        mode="MOCK",
        order_size=0.1,
        planner_buy_threshold=0.2,
        planner_sell_threshold=0.2,
        risk_max_notional_usd=20_000.0,
        risk_max_position_size=1.0,
        risk_max_drawdown_pct=0.15,
        risk_min_confidence=0.2,
        max_leverage=3.0,
        allowed_actions=("BUY", "SELL", "HOLD", "CLOSE"),
    )
    defaults.update(overrides)
    return StrategyConfig(**defaults)


def _plan(action="BUY", confidence=0.6, qty=0.05) -> PlannerDecision:
    return PlannerDecision(
        action=action,
        confidence=confidence,
        target_quantity=qty,
        rationale=("planner",),
        metrics={"signal": confidence},
    )


def _risk_approved(qty=0.05) -> RiskAssessment:
    return RiskAssessment(
        approved=True,
        approved_quantity=qty,
        signals=(
            RiskSignal(name="confidence_minimum", passed=True, value=0.6, limit=0.2, message="ok"),
            RiskSignal(
                name="notional_limit", passed=True, value=1000.0, limit=20_000.0, message="ok"
            ),
            RiskSignal(name="position_limit", passed=True, value=0.5, limit=1.0, message="ok"),
            RiskSignal(name="drawdown_limit", passed=True, value=0.01, limit=0.15, message="ok"),
        ),
        blocked_by=(),
        risk_score=0.0,
        rationale=("risk",),
    )


def _risk_blocked(*blocked_by: str) -> RiskAssessment:
    return RiskAssessment(
        approved=False,
        approved_quantity=0.0,
        signals=(),
        blocked_by=blocked_by,
        risk_score=1.0,
        rationale=("blocked",),
    )


def _decision(action="BUY", quantity=0.05, confidence=0.6) -> ExecutionDecision:
    return ExecutionDecision(
        action=action,
        quantity=quantity,
        confidence=confidence,
        rationale=("execution",),
        constraints={"schema_valid": True},
    )


def _ctx(**overrides) -> dict:
    defaults = dict(
        symbol="BTC/USDT",
        mid_price=42_000.0,
        current_position=0.0,
        equity_usd=10_000.0,
        drawdown_pct=0.01,
    )
    defaults.update(overrides)
    return defaults


# ═══════════════════════════════════════════════════════════════════════════════
# Guardrail — additional edge cases beyond test_p3_guardrail_validation.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestGuardrailQuantitySemantics:
    """Test _quantity_semantics_valid for each action."""

    def test_buy_positive_quantity_ok(self) -> None:
        assert (
            GuardrailValidationLayer._quantity_semantics_valid(action="BUY", quantity=0.1) is True
        )

    def test_buy_negative_quantity_bad(self) -> None:
        assert (
            GuardrailValidationLayer._quantity_semantics_valid(action="BUY", quantity=-0.1) is False
        )

    def test_buy_zero_quantity_bad(self) -> None:
        assert (
            GuardrailValidationLayer._quantity_semantics_valid(action="BUY", quantity=0.0) is False
        )

    def test_sell_negative_quantity_ok(self) -> None:
        assert (
            GuardrailValidationLayer._quantity_semantics_valid(action="SELL", quantity=-0.1) is True
        )

    def test_sell_positive_quantity_bad(self) -> None:
        assert (
            GuardrailValidationLayer._quantity_semantics_valid(action="SELL", quantity=0.1) is False
        )

    def test_close_nonzero_ok(self) -> None:
        assert (
            GuardrailValidationLayer._quantity_semantics_valid(action="CLOSE", quantity=-0.5)
            is True
        )

    def test_close_zero_bad(self) -> None:
        assert (
            GuardrailValidationLayer._quantity_semantics_valid(action="CLOSE", quantity=0.0)
            is False
        )

    def test_hold_zero_ok(self) -> None:
        assert (
            GuardrailValidationLayer._quantity_semantics_valid(action="HOLD", quantity=0.0) is True
        )

    def test_hold_nonzero_bad(self) -> None:
        assert (
            GuardrailValidationLayer._quantity_semantics_valid(action="HOLD", quantity=0.1) is False
        )

    def test_unknown_action_bad(self) -> None:
        assert (
            GuardrailValidationLayer._quantity_semantics_valid(action="YOLO", quantity=1.0) is False
        )


class TestGuardrailNotionalLimit:
    """Test guardrail notional limit enforcement."""

    def test_exceeds_notional_rejected(self) -> None:
        layer = GuardrailValidationLayer()
        # quantity=1.0 * mid_price=42000 = 42,000 > max_notional=20,000
        result = layer.validate(
            strategy=_strategy(risk_max_notional_usd=20_000.0),
            market_context=_ctx(mid_price=42_000.0),
            plan=_plan(qty=1.0),
            risk=_risk_approved(qty=1.0),
            decision=_decision(action="BUY", quantity=1.0),
        )
        assert result.allowed is False
        assert "notional_limit" in result.blocked_by

    def test_within_notional_allowed(self) -> None:
        layer = GuardrailValidationLayer()
        # quantity=0.01 * 42000 = 420 < 20000
        result = layer.validate(
            strategy=_strategy(risk_max_notional_usd=20_000.0),
            market_context=_ctx(mid_price=42_000.0),
            plan=_plan(qty=0.01),
            risk=_risk_approved(qty=0.01),
            decision=_decision(action="BUY", quantity=0.01),
        )
        assert result.allowed is True


class TestGuardrailPositionLimit:
    """Test guardrail position size enforcement."""

    def test_exceeds_position_rejected(self) -> None:
        layer = GuardrailValidationLayer()
        # current=0.9, buy=0.5, projected=1.4 > max_position=1.0
        result = layer.validate(
            strategy=_strategy(risk_max_position_size=1.0),
            market_context=_ctx(current_position=0.9),
            plan=_plan(qty=0.5),
            risk=_risk_approved(qty=0.5),
            decision=_decision(action="BUY", quantity=0.5),
        )
        assert result.allowed is False
        assert "position_limit" in result.blocked_by

    def test_within_position_allowed(self) -> None:
        layer = GuardrailValidationLayer()
        result = layer.validate(
            strategy=_strategy(risk_max_position_size=1.0, max_leverage=5.0),
            market_context=_ctx(current_position=0.5, equity_usd=50_000.0),
            plan=_plan(qty=0.3),
            risk=_risk_approved(qty=0.3),
            decision=_decision(action="BUY", quantity=0.3),
        )
        assert result.allowed is True


class TestGuardrailActionNotAllowed:
    """Test guardrail rejects actions not in strategy allowed_actions."""

    def test_sell_not_allowed(self) -> None:
        layer = GuardrailValidationLayer()
        result = layer.validate(
            strategy=_strategy(allowed_actions=("BUY", "HOLD")),
            market_context=_ctx(),
            plan=_plan(action="SELL", qty=-0.05),
            risk=_risk_approved(qty=-0.05),
            decision=_decision(action="SELL", quantity=-0.05),
        )
        assert result.allowed is False
        assert "action_schema" in result.blocked_by


class TestGuardrailHoldAction:
    """HOLD action should always pass guardrails (non-executable)."""

    def test_hold_always_passes(self) -> None:
        layer = GuardrailValidationLayer()
        result = layer.validate(
            strategy=_strategy(),
            market_context=_ctx(),
            plan=_plan(action="HOLD", qty=0.0),
            risk=_risk_blocked("confidence_minimum"),
            decision=_decision(action="HOLD", quantity=0.0, confidence=0.01),
        )
        # HOLD is not executable, so confidence_threshold and risk_alignment are skipped
        assert result.allowed is True


# ═══════════════════════════════════════════════════════════════════════════════
# Risk Agent — additional edge cases beyond test_p3_risk_agent.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestRiskAgentDrawdown:
    """Test drawdown limit enforcement."""

    def test_exceeds_drawdown_rejected(self) -> None:
        agent = RiskAgent()
        assessment = agent.evaluate(
            plan=_plan(action="BUY", qty=0.02, confidence=0.6),
            market_context={"mid_price": 42_000.0, "current_position": 0.0, "drawdown_pct": 0.25},
            strategy=_strategy(risk_max_drawdown_pct=0.15),
        )
        assert assessment.approved is False
        assert "drawdown_limit" in assessment.blocked_by

    def test_within_drawdown_allowed(self) -> None:
        agent = RiskAgent()
        assessment = agent.evaluate(
            plan=_plan(action="BUY", qty=0.02, confidence=0.6),
            market_context={"mid_price": 42_000.0, "current_position": 0.0, "drawdown_pct": 0.10},
            strategy=_strategy(risk_max_drawdown_pct=0.15),
        )
        assert assessment.approved is True


class TestRiskAgentPositionLimit:
    """Test position limit enforcement via risk agent."""

    def test_exceeds_position_rejected(self) -> None:
        agent = RiskAgent()
        assessment = agent.evaluate(
            plan=_plan(action="BUY", qty=0.8, confidence=0.6),
            market_context={"mid_price": 42_000.0, "current_position": 0.5, "drawdown_pct": 0.01},
            strategy=_strategy(risk_max_position_size=1.0),
        )
        # projected = 0.5 + 0.8 = 1.3 > 1.0
        assert assessment.approved is False
        assert "position_limit" in assessment.blocked_by


class TestRiskAgentMultipleSignals:
    """Test risk agent blocks on multiple simultaneous failures."""

    def test_multiple_blocks(self) -> None:
        agent = RiskAgent()
        assessment = agent.evaluate(
            plan=_plan(action="BUY", qty=0.8, confidence=0.05),
            market_context={"mid_price": 42_000.0, "current_position": 0.5, "drawdown_pct": 0.25},
            strategy=_strategy(
                risk_max_notional_usd=1_000.0,  # will fail: 0.8 * 42000 = 33600
                risk_max_position_size=1.0,  # will fail: 0.5 + 0.8 = 1.3
                risk_max_drawdown_pct=0.15,  # will fail: 0.25
                risk_min_confidence=0.2,  # will fail: 0.05
            ),
        )
        assert assessment.approved is False
        assert len(assessment.blocked_by) >= 3
        assert assessment.risk_score > 0.5


class TestRiskAgentActionablePlan:
    """Test actionable_plan signal: HOLD with zero qty should fail actionable check."""

    def test_hold_plan_fails_actionable(self) -> None:
        agent = RiskAgent()
        assessment = agent.evaluate(
            plan=_plan(action="HOLD", qty=0.0, confidence=0.8),
            market_context={"mid_price": 42_000.0, "current_position": 0.0, "drawdown_pct": 0.01},
            strategy=_strategy(),
        )
        assert assessment.approved is False
        assert "actionable_plan" in assessment.blocked_by

    def test_close_plan_passes_actionable(self) -> None:
        agent = RiskAgent()
        assessment = agent.evaluate(
            plan=_plan(action="CLOSE", qty=0.1, confidence=0.8),
            market_context={"mid_price": 42_000.0, "current_position": 0.1, "drawdown_pct": 0.01},
            strategy=_strategy(),
        )
        assert assessment.approved is True


class TestRiskAgentRationale:
    """Test risk assessment contains expected rationale fields."""

    def test_rationale_has_notional(self) -> None:
        agent = RiskAgent()
        assessment = agent.evaluate(
            plan=_plan(action="BUY", qty=0.02, confidence=0.6),
            market_context={"mid_price": 42_000.0, "current_position": 0.0, "drawdown_pct": 0.01},
            strategy=_strategy(),
        )
        rationale_text = " ".join(assessment.rationale)
        assert "proposed_notional" in rationale_text
        assert "projected_position" in rationale_text
        assert "drawdown_pct" in rationale_text


# ═══════════════════════════════════════════════════════════════════════════════
# Execution Decision Agent — additional edge cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestExecutionDecisionCloseScenarios:
    """Test CLOSE action edge cases."""

    def test_close_with_no_position_yields_zero(self) -> None:
        agent = ExecutionDecisionAgent()
        decision = agent.propose_action(
            plan=_plan(action="CLOSE", qty=0.0, confidence=0.8),
            risk=_risk_approved(qty=0.0),
            market_context={"current_position": 0.0, "mid_price": 42_000.0},
            strategy=_strategy(),
        )
        # CLOSE with 0 position → quantity=0 → normalized to HOLD
        assert decision.action == "HOLD"
        assert decision.quantity == 0.0

    def test_close_with_long_position_flattens(self) -> None:
        agent = ExecutionDecisionAgent()
        decision = agent.propose_action(
            plan=_plan(action="CLOSE", qty=0.0, confidence=0.8),
            risk=_risk_approved(qty=0.0),
            market_context={"current_position": 0.75, "mid_price": 42_000.0},
            strategy=_strategy(),
        )
        assert decision.action == "CLOSE"
        assert decision.quantity == -0.75


class TestExecutionDecisionNormalizeAction:
    """Test _normalize_action static method."""

    def test_valid_actions(self) -> None:
        for action in ALLOWED_ACTIONS:
            assert ExecutionDecisionAgent._normalize_action(action) == action

    def test_unknown_action_becomes_hold(self) -> None:
        assert ExecutionDecisionAgent._normalize_action("YOLO") == "HOLD"

    def test_case_insensitive(self) -> None:
        assert ExecutionDecisionAgent._normalize_action("buy") == "BUY"


class TestExecutionDecisionClampConfidence:
    """Test _clamp_confidence static method."""

    def test_clamps_above_one(self) -> None:
        assert ExecutionDecisionAgent._clamp_confidence(1.5) == 1.0

    def test_clamps_below_zero(self) -> None:
        assert ExecutionDecisionAgent._clamp_confidence(-0.5) == 0.0

    def test_in_range_passthrough(self) -> None:
        assert ExecutionDecisionAgent._clamp_confidence(0.7) == 0.7


class TestExecutionDecisionConstraints:
    """Test constraints dict output format."""

    def test_buy_constraints_schema_valid(self) -> None:
        agent = ExecutionDecisionAgent()
        decision = agent.propose_action(
            plan=_plan(action="BUY", qty=0.05, confidence=0.7),
            risk=_risk_approved(qty=0.05),
            market_context={"current_position": 0.0, "mid_price": 42_000.0},
            strategy=_strategy(mode="MOCK"),
        )
        assert decision.constraints["schema_valid"] is True
        assert decision.constraints["allowed_actions"] == list(ALLOWED_ACTIONS)
        assert decision.constraints["risk_approved"] is True
        assert decision.constraints["mode"] == "MOCK"

    def test_hold_constraints_schema_valid(self) -> None:
        agent = ExecutionDecisionAgent()
        decision = agent.propose_action(
            plan=_plan(action="BUY", qty=0.05, confidence=0.7),
            risk=_risk_blocked("notional_limit"),
            market_context={"current_position": 0.0, "mid_price": 42_000.0},
            strategy=_strategy(),
        )
        assert decision.action == "HOLD"
        assert decision.constraints["schema_valid"] is True
        assert decision.constraints["risk_approved"] is False
        assert "notional_limit" in decision.constraints["blocked_by"]


class TestExecutionDecisionQuantityFallback:
    """Test quantity resolution fallback chain."""

    def test_uses_plan_target_when_risk_qty_zero(self) -> None:
        agent = ExecutionDecisionAgent()
        risk = RiskAssessment(
            approved=True,
            approved_quantity=0.0,  # zero → fallback to plan.target_quantity
            signals=(),
            blocked_by=(),
            risk_score=0.0,
            rationale=(),
        )
        decision = agent.propose_action(
            plan=_plan(action="BUY", qty=0.08, confidence=0.7),
            risk=risk,
            market_context={"current_position": 0.0, "mid_price": 42_000.0},
            strategy=_strategy(order_size=0.2),
        )
        # Falls back to plan.target_quantity (0.08) since risk.approved_quantity is 0
        assert decision.quantity == 0.08

    def test_uses_default_size_when_all_zero(self) -> None:
        agent = ExecutionDecisionAgent()
        risk = RiskAssessment(
            approved=True,
            approved_quantity=0.0,
            signals=(),
            blocked_by=(),
            risk_score=0.0,
            rationale=(),
        )
        decision = agent.propose_action(
            plan=_plan(action="BUY", qty=0.0, confidence=0.7),
            risk=risk,
            market_context={"current_position": 0.0, "mid_price": 42_000.0},
            strategy=_strategy(order_size=0.2),
        )
        # Falls back to strategy.order_size
        assert decision.quantity == 0.2


class TestExecutionDecisionRationale:
    """Test execution decision rationale content."""

    def test_rationale_contains_planner_action(self) -> None:
        agent = ExecutionDecisionAgent()
        decision = agent.propose_action(
            plan=_plan(action="SELL", qty=-0.03, confidence=0.7),
            risk=_risk_approved(qty=-0.03),
            market_context={"current_position": 0.1, "mid_price": 42_000.0},
            strategy=_strategy(),
        )
        rationale_text = " ".join(decision.rationale)
        assert "planner_action=SELL" in rationale_text
        assert "final_action=SELL" in rationale_text

    def test_hold_rationale_contains_blocked_by(self) -> None:
        agent = ExecutionDecisionAgent()
        decision = agent.propose_action(
            plan=_plan(action="BUY", qty=0.05, confidence=0.7),
            risk=_risk_blocked("drawdown_limit", "confidence_minimum"),
            market_context={"current_position": 0.0, "mid_price": 42_000.0},
            strategy=_strategy(),
        )
        rationale_text = " ".join(decision.rationale)
        assert "risk_not_approved" in rationale_text
        assert "blocked_by=" in rationale_text
