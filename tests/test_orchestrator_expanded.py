"""Expanded tests for agent_orchestrator — contracts, market_context, memory_layer, orchestrator, planner, llm_runtime.

TEST-001: 30+ new tests covering context assembly, risk gating, memory ops, data contracts.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any
from unittest.mock import AsyncMock

import pytest

from services.agent_orchestrator.contracts import (
    ExecutionDecision,
    GuardrailValidationResult,
    GuardrailViolation,
    MarketContextOutput,
    OrchestrationResult,
    PlannerDecision,
    RiskAssessment,
    RiskSignal,
    StrategyConfig,
)
from services.agent_orchestrator.execution_decision_agent import ExecutionDecisionAgent
from services.agent_orchestrator.guardrail_validation import GuardrailValidationLayer
from services.agent_orchestrator.market_context_agent import MarketContextAgent
from services.agent_orchestrator.memory_layer import (
    AgentMemoryLayer,
    DecisionMemoryRecord,
    DecisionMemorySnapshot,
    _ensure_mapping,
    _normalize,
    _NoopLongTermMemoryStore,
    _NoopShortTermMemoryStore,
)
from services.agent_orchestrator.metrics_tracing import AgentRuntimeMetrics
from services.agent_orchestrator.planner_agent import PlannerAgent
from services.agent_orchestrator.risk_agent import RiskAgent
from services.agent_orchestrator.llm_runtime import (
    _optional_float,
    _optional_bool,
    _optional_upper,
    _normalize_rationale,
    _normalize_tokens,
    _parse_response_payload,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Shared factories
# ═══════════════════════════════════════════════════════════════════════════════


def _strategy(**overrides: Any) -> StrategyConfig:
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


def _plan(action: str = "BUY", confidence: float = 0.6, qty: float = 0.05) -> PlannerDecision:
    return PlannerDecision(
        action=action,
        confidence=confidence,
        target_quantity=qty,
        rationale=("planner",),
        metrics={"signal": confidence},
    )


def _risk_approved(qty: float = 0.05) -> RiskAssessment:
    return RiskAssessment(
        approved=True,
        approved_quantity=qty,
        signals=(
            RiskSignal(name="confidence_minimum", passed=True, value=0.6, limit=0.2, message="ok"),
            RiskSignal(name="actionable_plan", passed=True, value=1.0, limit=1.0, message="ok"),
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


def _decision(
    action: str = "BUY", quantity: float = 0.05, confidence: float = 0.6
) -> ExecutionDecision:
    return ExecutionDecision(
        action=action,
        quantity=quantity,
        confidence=confidence,
        rationale=("execution",),
        constraints={"schema_valid": True},
    )


def _ctx(**overrides: Any) -> dict[str, Any]:
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
# Contracts — dataclass construction, validation, immutability
# ═══════════════════════════════════════════════════════════════════════════════


class TestStrategyConfig:
    """Test StrategyConfig dataclass construction and defaults."""

    def test_default_max_leverage(self) -> None:
        s = _strategy()
        assert s.max_leverage == 3.0

    def test_default_allowed_actions(self) -> None:
        s = _strategy()
        assert s.allowed_actions == ("BUY", "SELL", "HOLD", "CLOSE")

    def test_override_defaults(self) -> None:
        s = _strategy(max_leverage=10.0, allowed_actions=("BUY", "HOLD"))
        assert s.max_leverage == 10.0
        assert s.allowed_actions == ("BUY", "HOLD")

    def test_frozen(self) -> None:
        s = _strategy()
        with pytest.raises(AttributeError):
            s.strategy_id = "other"  # type: ignore[misc]

    def test_asdict_roundtrip(self) -> None:
        s = _strategy()
        d = asdict(s)
        reconstructed = StrategyConfig(**d)
        assert reconstructed == s


class TestPlannerDecision:
    """Test PlannerDecision dataclass."""

    def test_construction(self) -> None:
        d = PlannerDecision(
            action="BUY",
            confidence=0.7,
            target_quantity=0.1,
            rationale=("reason1", "reason2"),
            metrics={"x": 1.0},
        )
        assert d.action == "BUY"
        assert d.confidence == 0.7
        assert d.rationale == ("reason1", "reason2")

    def test_frozen(self) -> None:
        d = _plan()
        with pytest.raises(AttributeError):
            d.action = "SELL"  # type: ignore[misc]

    def test_rationale_is_tuple(self) -> None:
        d = _plan()
        assert isinstance(d.rationale, tuple)


class TestRiskSignal:
    """Test RiskSignal dataclass."""

    def test_construction(self) -> None:
        s = RiskSignal(name="test", passed=True, value=0.5, limit=1.0, message="ok")
        assert s.name == "test"
        assert s.passed is True

    def test_frozen(self) -> None:
        s = RiskSignal(name="test", passed=True, value=0.5, limit=1.0, message="ok")
        with pytest.raises(AttributeError):
            s.passed = False  # type: ignore[misc]


class TestRiskAssessment:
    """Test RiskAssessment dataclass."""

    def test_approved_quantity_zero_when_blocked(self) -> None:
        a = _risk_blocked("confidence_minimum")
        assert a.approved is False
        assert a.approved_quantity == 0.0

    def test_blocked_by_is_tuple(self) -> None:
        a = _risk_blocked("a", "b")
        assert a.blocked_by == ("a", "b")


class TestExecutionDecision:
    """Test ExecutionDecision dataclass."""

    def test_construction(self) -> None:
        d = _decision(action="SELL", quantity=-0.1, confidence=0.8)
        assert d.action == "SELL"
        assert d.quantity == -0.1

    def test_constraints_dict(self) -> None:
        d = _decision()
        assert isinstance(d.constraints, dict)


class TestGuardrailViolation:
    """Test GuardrailViolation dataclass."""

    def test_construction(self) -> None:
        v = GuardrailViolation(code="test_code", message="test msg", details={"k": "v"})
        assert v.code == "test_code"
        assert v.details == {"k": "v"}


class TestGuardrailValidationResult:
    """Test GuardrailValidationResult dataclass."""

    def test_allowed_no_violations(self) -> None:
        r = GuardrailValidationResult(
            allowed=True,
            blocked_by=(),
            violations=(),
            checks={"a": True},
        )
        assert r.allowed is True
        assert len(r.blocked_by) == 0

    def test_blocked_has_violations(self) -> None:
        v = GuardrailViolation(code="x", message="m", details={})
        r = GuardrailValidationResult(
            allowed=False,
            blocked_by=("x",),
            violations=(v,),
            checks={"a": False},
        )
        assert r.allowed is False
        assert "x" in r.blocked_by


class TestMarketContextOutput:
    """Test MarketContextOutput dataclass."""

    def test_construction(self) -> None:
        o = MarketContextOutput(
            context={"mid_price": 100.0},
            microstructure={"spread_bps": 1.0},
            news={"summary": "ok"},
            quality={"has_orderbook": True},
            notes=("note1",),
        )
        assert o.context["mid_price"] == 100.0
        assert o.notes == ("note1",)


class TestOrchestrationResult:
    """Test OrchestrationResult dataclass."""

    def test_construction(self) -> None:
        market_ctx = MarketContextOutput(
            context={},
            microstructure={},
            news={},
            quality={},
            notes=(),
        )
        r = OrchestrationResult(
            trace_id="t1",
            decision_id="d1",
            mode="MOCK",
            status="RISK_APPROVED",
            lifecycle=(),
            market_context=market_ctx,
            plan=_plan(),
            risk=_risk_approved(),
            execution_decision=_decision(),
            guardrail=GuardrailValidationResult(
                allowed=True,
                blocked_by=(),
                violations=(),
                checks={},
            ),
            execution_intent=None,
        )
        assert r.trace_id == "t1"
        assert r.status == "RISK_APPROVED"
        assert r.execution_intent is None


class TestDecisionMemoryRecord:
    """Test DecisionMemoryRecord dataclass."""

    def test_construction(self) -> None:
        rec = DecisionMemoryRecord(
            trace_id="t1",
            decision_id="d1",
            strategy_id="s1",
            mode="MOCK",
            status="OK",
            summary={"a": 1},
            lifecycle=(),
            persisted_at="2024-01-01T00:00:00Z",
        )
        assert rec.trace_id == "t1"
        assert rec.summary == {"a": 1}


class TestDecisionMemorySnapshot:
    """Test DecisionMemorySnapshot dataclass."""

    def test_empty_snapshot(self) -> None:
        snap = DecisionMemorySnapshot(
            mode="MOCK",
            strategy_id="s1",
            decision_id="d1",
            source="empty",
            slots={},
        )
        assert snap.source == "empty"
        assert len(snap.slots) == 0

    def test_redis_snapshot(self) -> None:
        snap = DecisionMemorySnapshot(
            mode="MOCK",
            strategy_id="s1",
            decision_id="d1",
            source="redis",
            slots={"context": {"mid_price": 100}},
        )
        assert snap.source == "redis"
        assert snap.slots["context"]["mid_price"] == 100


# ═══════════════════════════════════════════════════════════════════════════════
# MarketContextAgent — level extraction, context building, edge cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractLevel:
    """Test _extract_level with various orderbook states."""

    def test_empty_list(self) -> None:
        price, size = MarketContextAgent._extract_level([], side="bid")
        assert price is None
        assert size == 0.0

    def test_none_input(self) -> None:
        price, size = MarketContextAgent._extract_level(None, side="bid")  # type: ignore[arg-type]
        assert price is None
        assert size == 0.0

    def test_non_list_input(self) -> None:
        price, size = MarketContextAgent._extract_level("not a list", side="bid")  # type: ignore[arg-type]
        assert price is None
        assert size == 0.0

    def test_malformed_entries_skipped(self) -> None:
        levels = [
            "not_a_mapping",
            {"price": "bad", "amount": "1"},
            42,
        ]
        price, size = MarketContextAgent._extract_level(levels, side="bid")
        assert price is None
        assert size == 0.0

    def test_missing_keys_skipped(self) -> None:
        levels = [{"price": "100"}, {"amount": "5"}]  # missing amount, missing price
        price, size = MarketContextAgent._extract_level(levels, side="bid")
        assert price is None
        assert size == 0.0

    def test_bid_returns_highest_price(self) -> None:
        levels = [
            {"price": "100.0", "amount": "1.0"},
            {"price": "101.0", "amount": "2.0"},
            {"price": "99.0", "amount": "3.0"},
        ]
        price, size = MarketContextAgent._extract_level(levels, side="bid")
        assert price == 101.0
        assert size == 2.0

    def test_ask_returns_lowest_price(self) -> None:
        levels = [
            {"price": "100.0", "amount": "1.0"},
            {"price": "101.0", "amount": "2.0"},
            {"price": "99.0", "amount": "3.0"},
        ]
        price, size = MarketContextAgent._extract_level(levels, side="ask")
        assert price == 99.0
        assert size == 3.0

    def test_negative_size_clamped_to_zero(self) -> None:
        levels = [{"price": "100", "amount": "-5"}]
        price, size = MarketContextAgent._extract_level(levels, side="bid")
        assert price == 100.0
        assert size == 0.0

    def test_single_entry(self) -> None:
        levels = [{"price": "50000", "amount": "0.5"}]
        price, size = MarketContextAgent._extract_level(levels, side="bid")
        assert price == 50000.0
        assert size == 0.5

    def test_numeric_types_accepted(self) -> None:
        levels = [{"price": 100, "amount": 1.5}]
        price, size = MarketContextAgent._extract_level(levels, side="bid")
        assert price == 100.0
        assert size == 1.5


class TestMicrostructureRegime:
    """Test _microstructure_regime classification."""

    def test_no_orderbook_unknown(self) -> None:
        r = MarketContextAgent._microstructure_regime(has_orderbook=False, orderbook_imbalance=0.5)
        assert r == "unknown"

    def test_bid_dominant(self) -> None:
        r = MarketContextAgent._microstructure_regime(has_orderbook=True, orderbook_imbalance=0.3)
        assert r == "bid_dominant"

    def test_ask_dominant(self) -> None:
        r = MarketContextAgent._microstructure_regime(has_orderbook=True, orderbook_imbalance=-0.3)
        assert r == "ask_dominant"

    def test_balanced(self) -> None:
        r = MarketContextAgent._microstructure_regime(has_orderbook=True, orderbook_imbalance=0.0)
        assert r == "balanced"

    def test_boundary_bid_dominant(self) -> None:
        r = MarketContextAgent._microstructure_regime(has_orderbook=True, orderbook_imbalance=0.2)
        assert r == "bid_dominant"

    def test_boundary_ask_dominant(self) -> None:
        r = MarketContextAgent._microstructure_regime(has_orderbook=True, orderbook_imbalance=-0.2)
        assert r == "ask_dominant"


class TestContextScore:
    """Test _context_score calculation."""

    def test_both_present(self) -> None:
        assert MarketContextAgent._context_score(has_orderbook=True, has_news=True) == 1.0

    def test_only_orderbook(self) -> None:
        assert MarketContextAgent._context_score(has_orderbook=True, has_news=False) == 0.8

    def test_only_news(self) -> None:
        assert MarketContextAgent._context_score(has_orderbook=False, has_news=True) == 0.2

    def test_neither(self) -> None:
        assert MarketContextAgent._context_score(has_orderbook=False, has_news=False) == 0.0


class TestBuildContext:
    """Test MarketContextAgent.enrich with various payloads."""

    def test_full_payload(self) -> None:
        agent = MarketContextAgent()
        payload = {
            "bids": [{"price": "100", "amount": "1"}],
            "asks": [{"price": "101", "amount": "2"}],
            "news": {"summary": "BTC up", "sentiment": 0.8, "source_count": 3},
            "symbol": "BTC/USDT",
            "exchange": "binance",
            "current_position": 0.5,
            "drawdown_pct": 0.02,
            "timestamp_ms": 1700000000000,
        }
        result = agent.enrich(payload=payload, strategy=_strategy())
        assert result.context["best_bid"] == 100.0
        assert result.context["best_ask"] == 101.0
        assert result.context["mid_price"] == 100.5
        assert result.quality["has_orderbook"] is True
        assert result.quality["has_news"] is True
        assert result.quality["context_score"] == 1.0
        assert len(result.notes) == 0

    def test_no_orderbook_fallback_mid_price(self) -> None:
        agent = MarketContextAgent()
        payload = {"mid_price": 50000.0}
        result = agent.enrich(payload=payload, strategy=_strategy())
        assert result.context["mid_price"] == 50000.0
        assert result.context["best_bid"] is None
        assert result.quality["has_orderbook"] is False
        assert "orderbook_unavailable" in result.notes

    def test_no_news_fallback(self) -> None:
        agent = MarketContextAgent()
        payload = {
            "bids": [{"price": "100", "amount": "1"}],
            "asks": [{"price": "101", "amount": "1"}],
        }
        result = agent.enrich(payload=payload, strategy=_strategy())
        assert result.quality["has_news"] is False
        assert "news_unavailable" in result.notes

    def test_news_empty_summary_is_fallback(self) -> None:
        agent = MarketContextAgent()
        payload = {
            "bids": [{"price": "100", "amount": "1"}],
            "asks": [{"price": "101", "amount": "1"}],
            "news": {"summary": "  ", "sentiment": 0.0},
        }
        result = agent.enrich(payload=payload, strategy=_strategy())
        assert result.quality["has_news"] is False

    def test_spread_bps_calculation(self) -> None:
        agent = MarketContextAgent()
        payload = {
            "bids": [{"price": "100", "amount": "1"}],
            "asks": [{"price": "102", "amount": "1"}],
        }
        result = agent.enrich(payload=payload, strategy=_strategy())
        # spread = (102 - 100) / 101 * 10000 = ~198.02 bps
        assert result.context["spread_bps"] > 190.0
        assert result.context["spread_bps"] < 210.0

    def test_orderbook_imbalance_calculation(self) -> None:
        agent = MarketContextAgent()
        payload = {
            "bids": [{"price": "100", "amount": "3"}],
            "asks": [{"price": "101", "amount": "1"}],
        }
        result = agent.enrich(payload=payload, strategy=_strategy())
        # imbalance = (3 - 1) / 4 = 0.5
        assert result.context["orderbook_imbalance"] == 0.5
        assert result.microstructure["regime"] == "bid_dominant"

    def test_symbol_from_strategy_fallback(self) -> None:
        agent = MarketContextAgent()
        payload = {}
        result = agent.enrich(payload=payload, strategy=_strategy(symbol="ETH/USDT"))
        assert result.context["symbol"] == "ETH/USDT"

    def test_exchange_default_unknown(self) -> None:
        agent = MarketContextAgent()
        payload = {}
        result = agent.enrich(payload=payload, strategy=_strategy())
        assert result.context["exchange"] == "unknown"


class TestExtractNews:
    """Test _extract_news edge cases."""

    def test_news_not_mapping(self) -> None:
        agent = MarketContextAgent()
        summary, sentiment, count, fallback = agent._extract_news({"news": "not_a_mapping"})
        assert fallback is True
        assert summary == "news_unavailable"

    def test_news_none(self) -> None:
        agent = MarketContextAgent()
        summary, sentiment, count, fallback = agent._extract_news({"news": None})
        assert fallback is True

    def test_news_valid(self) -> None:
        agent = MarketContextAgent()
        summary, sentiment, count, fallback = agent._extract_news(
            {"news": {"summary": "good", "sentiment": 0.5, "source_count": 2}}
        )
        assert fallback is False
        assert summary == "good"
        assert sentiment == 0.5
        assert count == 2

    def test_news_sentiment_invalid_defaults_zero(self) -> None:
        agent = MarketContextAgent()
        _, sentiment, _, _ = agent._extract_news({"news": {"summary": "ok", "sentiment": "bad"}})
        assert sentiment == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# PlannerAgent — action selection, quantity, confidence
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlannerAgentAction:
    """Test PlannerAgent._select_action."""

    def test_buy_above_threshold(self) -> None:
        assert (
            PlannerAgent._select_action(
                imbalance=0.3, strategy=_strategy(planner_buy_threshold=0.2)
            )
            == "BUY"
        )

    def test_sell_below_threshold(self) -> None:
        assert (
            PlannerAgent._select_action(
                imbalance=-0.3, strategy=_strategy(planner_sell_threshold=0.2)
            )
            == "SELL"
        )

    def test_hold_between_thresholds(self) -> None:
        assert PlannerAgent._select_action(imbalance=0.1, strategy=_strategy()) == "HOLD"

    def test_exact_buy_threshold(self) -> None:
        assert (
            PlannerAgent._select_action(
                imbalance=0.2, strategy=_strategy(planner_buy_threshold=0.2)
            )
            == "BUY"
        )

    def test_exact_sell_threshold(self) -> None:
        assert (
            PlannerAgent._select_action(
                imbalance=-0.2, strategy=_strategy(planner_sell_threshold=0.2)
            )
            == "SELL"
        )

    def test_zero_imbalance_hold(self) -> None:
        assert PlannerAgent._select_action(imbalance=0.0, strategy=_strategy()) == "HOLD"


class TestPlannerAgentBuildPlan:
    """Test PlannerAgent.build_plan."""

    def test_buy_plan_quantity_positive(self) -> None:
        agent = PlannerAgent()
        decision = agent.build_plan(
            market_context={"best_bid_size": 10.0, "best_ask_size": 2.0, "mid_price": 50000.0},
            strategy=_strategy(order_size=0.1, planner_buy_threshold=0.2, risk_min_confidence=0.2),
        )
        assert decision.action == "BUY"
        assert decision.target_quantity > 0

    def test_sell_plan_quantity_negative(self) -> None:
        agent = PlannerAgent()
        decision = agent.build_plan(
            market_context={"best_bid_size": 2.0, "best_ask_size": 10.0, "mid_price": 50000.0},
            strategy=_strategy(order_size=0.1, planner_sell_threshold=0.2, risk_min_confidence=0.2),
        )
        assert decision.action == "SELL"
        assert decision.target_quantity < 0

    def test_hold_plan_quantity_zero(self) -> None:
        agent = PlannerAgent()
        decision = agent.build_plan(
            market_context={"best_bid_size": 5.0, "best_ask_size": 5.0, "mid_price": 50000.0},
            strategy=_strategy(),
        )
        assert decision.action == "HOLD"
        assert decision.target_quantity == 0.0

    def test_missing_sizes_default_zero(self) -> None:
        agent = PlannerAgent()
        decision = agent.build_plan(
            market_context={"mid_price": 50000.0},
            strategy=_strategy(),
        )
        # Both sizes 0 → imbalance 0 → HOLD
        assert decision.action == "HOLD"

    def test_confidence_is_clamped(self) -> None:
        agent = PlannerAgent()
        decision = agent.build_plan(
            market_context={"best_bid_size": 100.0, "best_ask_size": 0.0, "mid_price": 50000.0},
            strategy=_strategy(order_size=0.1, planner_buy_threshold=0.0, risk_min_confidence=0.1),
        )
        # imbalance = 1.0 → confidence = 1.0
        assert decision.confidence == 1.0

    def test_metrics_include_imbalance(self) -> None:
        agent = PlannerAgent()
        decision = agent.build_plan(
            market_context={"best_bid_size": 10.0, "best_ask_size": 5.0, "mid_price": 100.0},
            strategy=_strategy(planner_buy_threshold=0.0),
        )
        assert "orderbook_imbalance" in decision.metrics
        assert decision.metrics["mid_price"] == 100.0


# ═══════════════════════════════════════════════════════════════════════════════
# MemoryLayer — short/long term store, noop stores, persistence
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoopShortTermMemoryStore:
    """Test _NoopShortTermMemoryStore defaults."""

    @pytest.mark.asyncio
    async def test_write_is_noop(self) -> None:
        store = _NoopShortTermMemoryStore()
        await store.write_slot(
            mode="MOCK",
            strategy_id="s1",
            decision_id="d1",
            slot="test",
            payload={"k": "v"},
            ttl_seconds=60,
        )
        # No error, no state change

    @pytest.mark.asyncio
    async def test_read_returns_empty(self) -> None:
        store = _NoopShortTermMemoryStore()
        result = await store.read_slots(mode="MOCK", strategy_id="s1", decision_id="d1")
        assert result == {}


class TestNoopLongTermMemoryStore:
    """Test _NoopLongTermMemoryStore defaults."""

    @pytest.mark.asyncio
    async def test_persist_is_noop(self) -> None:
        store = _NoopLongTermMemoryStore()
        rec = DecisionMemoryRecord(
            trace_id="t1",
            decision_id="d1",
            strategy_id="s1",
            mode="MOCK",
            status="OK",
            summary={},
            lifecycle=(),
            persisted_at="2024-01-01T00:00:00Z",
        )
        await store.persist_decision_summary(rec)

    @pytest.mark.asyncio
    async def test_read_returns_none(self) -> None:
        store = _NoopLongTermMemoryStore()
        result = await store.read_decision_summary(decision_id="d1")
        assert result is None


class TestAgentMemoryLayerDefaults:
    """Test AgentMemoryLayer with default noop stores."""

    def test_default_stores(self) -> None:
        layer = AgentMemoryLayer()
        assert isinstance(layer.short_term_store, _NoopShortTermMemoryStore)
        assert isinstance(layer.long_term_store, _NoopLongTermMemoryStore)
        assert layer.decision_ttl_seconds == 900

    def test_custom_ttl(self) -> None:
        layer = AgentMemoryLayer(decision_ttl_seconds=300)
        assert layer.decision_ttl_seconds == 300

    @pytest.mark.asyncio
    async def test_read_empty_memory(self) -> None:
        layer = AgentMemoryLayer()
        snapshot = await layer.read_decision_memory(
            mode="MOCK",
            strategy_id="s1",
            decision_id="d1",
        )
        assert snapshot.source == "empty"
        assert snapshot.slots == {}

    @pytest.mark.asyncio
    async def test_write_decision_slot(self) -> None:
        mock_short = AsyncMock()
        mock_short.read_slots = AsyncMock(return_value={})
        layer = AgentMemoryLayer(short_term_store=mock_short)
        await layer.write_decision_slot(
            mode="MOCK",
            strategy_id="s1",
            decision_id="d1",
            slot="test",
            payload={"k": "v"},
        )
        mock_short.write_slot.assert_called_once()
        call_kwargs = mock_short.write_slot.call_args
        assert call_kwargs.kwargs["slot"] == "test"
        assert call_kwargs.kwargs["ttl_seconds"] == 900


class TestAgentMemoryLayerWithMockStore:
    """Test AgentMemoryLayer with mock short-term store (simulating redis hits)."""

    @pytest.mark.asyncio
    async def test_read_from_short_term(self) -> None:
        mock_short = AsyncMock()
        mock_short.read_slots = AsyncMock(
            return_value={
                "context": {"mid_price": 100.0},
                "plan": {"action": "BUY"},
            }
        )
        mock_long = AsyncMock()
        mock_long.read_decision_summary = AsyncMock(return_value=None)
        layer = AgentMemoryLayer(short_term_store=mock_short, long_term_store=mock_long)
        snapshot = await layer.read_decision_memory(
            mode="MOCK",
            strategy_id="s1",
            decision_id="d1",
        )
        assert snapshot.source == "redis"
        assert "context" in snapshot.slots
        assert snapshot.slots["context"]["mid_price"] == 100.0

    @pytest.mark.asyncio
    async def test_fallback_to_long_term(self) -> None:
        mock_short = AsyncMock()
        mock_short.read_slots = AsyncMock(return_value={})
        mock_short.write_slot = AsyncMock()
        archived = DecisionMemoryRecord(
            trace_id="t1",
            decision_id="d1",
            strategy_id="s1",
            mode="MOCK",
            status="OK",
            summary={"status": "OK", "market_context": {"mid": 50}},
            lifecycle=(),
            persisted_at="2024-01-01T00:00:00Z",
        )
        mock_long = AsyncMock()
        mock_long.read_decision_summary = AsyncMock(return_value=archived)
        layer = AgentMemoryLayer(short_term_store=mock_short, long_term_store=mock_long)
        snapshot = await layer.read_decision_memory(
            mode="MOCK",
            strategy_id="s1",
            decision_id="d1",
        )
        assert snapshot.source == "postgres"
        assert "summary" in snapshot.slots
        # Should write back to short-term cache
        mock_short.write_slot.assert_called_once()


class TestAgentMemoryLayerPersistDecision:
    """Test persist_decision_summary."""

    @pytest.mark.asyncio
    async def test_persist_creates_record(self) -> None:
        mock_short = AsyncMock()
        mock_long = AsyncMock()
        layer = AgentMemoryLayer(short_term_store=mock_short, long_term_store=mock_long)
        record = await layer.persist_decision_summary(
            trace_id="t1",
            decision_id="d1",
            strategy_id="s1",
            mode="MOCK",
            status="RISK_APPROVED",
            market_context={"mid_price": 100},
            plan={"action": "BUY", "confidence": 0.7},
            risk={"approved": True},
            execution_decision={"action": "BUY"},
            guardrail={"allowed": True},
            lifecycle=(),
        )
        assert record.trace_id == "t1"
        assert record.status == "RISK_APPROVED"
        assert "market_context" in record.summary
        mock_long.persist_decision_summary.assert_called_once()
        mock_short.write_slot.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# _normalize / _ensure_mapping — recursive dataclass handling
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalize:
    """Test _normalize and _ensure_mapping helpers."""

    def test_dict_passthrough(self) -> None:
        assert _normalize({"a": 1}) == {"a": 1}

    def test_tuple_to_list(self) -> None:
        assert _normalize((1, 2, 3)) == [1, 2, 3]

    def test_dataclass_to_dict(self) -> None:
        d = _normalize(RiskSignal(name="test", passed=True, value=0.5, limit=1.0, message="ok"))
        assert isinstance(d, dict)
        assert d["name"] == "test"
        assert d["passed"] is True

    def test_nested_dataclass(self) -> None:
        d = _normalize(_risk_approved())
        assert isinstance(d, dict)
        assert isinstance(d["signals"], list)
        assert d["approved"] is True

    def test_scalar_passthrough(self) -> None:
        assert _normalize(42) == 42
        assert _normalize("hello") == "hello"

    def test_ensure_mapping_wraps_non_dict(self) -> None:
        result = _ensure_mapping(42)
        assert result == {"value": 42}

    def test_ensure_mapping_passes_dict(self) -> None:
        result = _ensure_mapping({"a": 1})
        assert result == {"a": 1}


# ═══════════════════════════════════════════════════════════════════════════════
# MetricsTracing — record success/failure, snapshot
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentRuntimeMetrics:
    """Test AgentRuntimeMetrics tracking."""

    def test_record_success(self) -> None:
        m = AgentRuntimeMetrics()
        m.record_stage_success(
            trace_id="t1",
            decision_id="d1",
            mode="MOCK",
            stage="planner",
            latency_ms=5.0,
        )
        snap = m.snapshot()
        assert snap["agent_stages"]["planner"]["runs_total"] == 1
        assert snap["agent_stages"]["planner"]["failures_total"] == 0

    def test_record_failure(self) -> None:
        m = AgentRuntimeMetrics()
        m.record_stage_failure(
            trace_id="t1",
            decision_id="d1",
            mode="MOCK",
            stage="risk",
            latency_ms=2.0,
            error_type="ValueError",
        )
        snap = m.snapshot()
        assert snap["agent_stages"]["risk"]["failures_total"] == 1
        assert snap["agent_stages"]["risk"]["failure_rate"] == 1.0

    def test_avg_latency(self) -> None:
        m = AgentRuntimeMetrics()
        m.record_stage_success(
            trace_id="t1", decision_id="d1", mode="MOCK", stage="s", latency_ms=10.0
        )
        m.record_stage_success(
            trace_id="t1", decision_id="d1", mode="MOCK", stage="s", latency_ms=20.0
        )
        snap = m.snapshot()
        assert snap["agent_stages"]["s"]["avg_latency_ms"] == 15.0
        assert snap["agent_stages"]["s"]["max_latency_ms"] == 20.0

    def test_llm_call_tracking(self) -> None:
        m = AgentRuntimeMetrics()
        m.record_llm_call(
            trace_id="t1",
            decision_id="d1",
            strategy_id="s1",
            agent_name="planner",
            provider="openai",
            model="gpt-4",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            latency_ms=200.0,
            estimated_cost=0.01,
            status="succeeded",
        )
        snap = m.snapshot()
        assert snap["llm_usage"]["totals"]["calls_total"] == 1
        assert snap["llm_usage"]["totals"]["tokens_total"] == 150

    def test_llm_failed_call(self) -> None:
        m = AgentRuntimeMetrics()
        m.record_llm_call(
            trace_id="t1",
            decision_id="d1",
            strategy_id="s1",
            agent_name="planner",
            provider="openai",
            model="gpt-4",
            prompt_tokens=100,
            completion_tokens=0,
            total_tokens=100,
            latency_ms=50.0,
            estimated_cost=0.0,
            status="failed",
        )
        snap = m.snapshot()
        assert snap["llm_usage"]["totals"]["failed_calls_total"] == 1

    def test_recent_spans_capped(self) -> None:
        m = AgentRuntimeMetrics()
        for i in range(150):
            m.record_stage_success(
                trace_id="t1",
                decision_id=f"d{i}",
                mode="MOCK",
                stage="s",
                latency_ms=1.0,
            )
        snap = m.snapshot()
        assert len(snap["recent_spans"]) == 100


# ═══════════════════════════════════════════════════════════════════════════════
# LLM runtime helpers — _optional_*, _normalize_*, _parse_response_payload
# ═══════════════════════════════════════════════════════════════════════════════


class TestOptionalFloat:
    def test_none(self) -> None:
        assert _optional_float(None) is None

    def test_valid(self) -> None:
        assert _optional_float(3.14) == 3.14

    def test_string_number(self) -> None:
        assert _optional_float("2.5") == 2.5

    def test_invalid_string(self) -> None:
        assert _optional_float("abc") is None

    def test_list(self) -> None:
        assert _optional_float([1, 2]) is None


class TestOptionalBool:
    def test_true(self) -> None:
        assert _optional_bool(True) is True

    def test_false(self) -> None:
        assert _optional_bool(False) is False

    def test_string_true(self) -> None:
        assert _optional_bool("yes") is True

    def test_string_false(self) -> None:
        assert _optional_bool("no") is False

    def test_none(self) -> None:
        assert _optional_bool(None) is None

    def test_int(self) -> None:
        assert _optional_bool(1) is None


class TestOptionalUpper:
    def test_none(self) -> None:
        assert _optional_upper(None) is None

    def test_valid(self) -> None:
        assert _optional_upper("buy") == "BUY"

    def test_empty_string(self) -> None:
        assert _optional_upper("  ") is None

    def test_non_string(self) -> None:
        assert _optional_upper(42) is None


class TestNormalizeRationale:
    def test_valid_list(self) -> None:
        assert _normalize_rationale(["a", "b"]) == ("a", "b")

    def test_not_list(self) -> None:
        assert _normalize_rationale("not a list") == ()

    def test_empty_strings_filtered(self) -> None:
        assert _normalize_rationale(["a", "", "  ", "b"]) == ("a", "b")


class TestNormalizeTokens:
    def test_valid(self) -> None:
        assert _normalize_tokens(["x", "y"]) == ("x", "y")

    def test_not_list(self) -> None:
        assert _normalize_tokens("bad") == ()

    def test_empty_filtered(self) -> None:
        assert _normalize_tokens(["a", "", "b"]) == ("a", "b")


class TestParseResponsePayload:
    def test_empty_string(self) -> None:
        assert _parse_response_payload("") == {}

    def test_whitespace(self) -> None:
        assert _parse_response_payload("   ") == {}

    def test_valid_json(self) -> None:
        result = _parse_response_payload('{"action": "BUY"}')
        assert result == {"action": "BUY"}

    def test_invalid_json(self) -> None:
        assert _parse_response_payload("not json") == {}

    def test_json_array(self) -> None:
        assert _parse_response_payload("[1, 2]") == {}


# ═══════════════════════════════════════════════════════════════════════════════
# RiskAgent — boundary values and edge cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestRiskAgentEdgeCases:
    """Additional risk agent edge cases."""

    def test_zero_mid_price(self) -> None:
        agent = RiskAgent()
        assessment = agent.evaluate(
            plan=_plan(action="BUY", qty=0.1, confidence=0.6),
            market_context={"mid_price": 0.0, "current_position": 0.0, "drawdown_pct": 0.0},
            strategy=_strategy(),
        )
        assert assessment.approved is True

    def test_risk_score_proportional_to_blocks(self) -> None:
        agent = RiskAgent()
        # Fail only confidence
        a1 = agent.evaluate(
            plan=_plan(action="BUY", qty=0.01, confidence=0.05),
            market_context={"mid_price": 100.0, "current_position": 0.0, "drawdown_pct": 0.0},
            strategy=_strategy(risk_min_confidence=0.5),
        )
        # Fail confidence + drawdown
        a2 = agent.evaluate(
            plan=_plan(action="BUY", qty=0.01, confidence=0.05),
            market_context={"mid_price": 100.0, "current_position": 0.0, "drawdown_pct": 0.5},
            strategy=_strategy(risk_min_confidence=0.5, risk_max_drawdown_pct=0.1),
        )
        assert a2.risk_score > a1.risk_score

    def test_negative_drawdown_clamped(self) -> None:
        agent = RiskAgent()
        assessment = agent.evaluate(
            plan=_plan(action="BUY", qty=0.01, confidence=0.6),
            market_context={"mid_price": 100.0, "current_position": 0.0, "drawdown_pct": -0.1},
            strategy=_strategy(risk_max_drawdown_pct=0.15),
        )
        # Negative drawdown is < limit, so drawdown_limit should pass
        assert "drawdown_limit" not in assessment.blocked_by


# ═══════════════════════════════════════════════════════════════════════════════
# ExecutionDecisionAgent — SELL with position, boundary qty
# ═══════════════════════════════════════════════════════════════════════════════


class TestExecutionDecisionAgentEdge:
    """Additional execution decision agent edge cases."""

    def test_sell_with_position(self) -> None:
        agent = ExecutionDecisionAgent()
        decision = agent.propose_action(
            plan=_plan(action="SELL", qty=-0.05, confidence=0.8),
            risk=_risk_approved(qty=-0.05),
            market_context={"current_position": 0.1, "mid_price": 42_000.0},
            strategy=_strategy(),
        )
        assert decision.action == "SELL"
        assert decision.quantity < 0

    def test_normalize_sell_positive_to_hold(self) -> None:
        action, qty = ExecutionDecisionAgent._normalize_action_quantity(
            action="SELL", quantity=0.05
        )
        assert action == "HOLD"
        assert qty == 0.0

    def test_normalize_buy_zero_to_hold(self) -> None:
        action, qty = ExecutionDecisionAgent._normalize_action_quantity(action="BUY", quantity=0.0)
        assert action == "HOLD"
        assert qty == 0.0

    def test_normalize_close_nonzero_ok(self) -> None:
        action, qty = ExecutionDecisionAgent._normalize_action_quantity(
            action="CLOSE", quantity=-0.5
        )
        assert action == "CLOSE"
        assert qty == -0.5


# ═══════════════════════════════════════════════════════════════════════════════
# GuardrailValidationLayer — leverage limit, symbol constraint
# ═══════════════════════════════════════════════════════════════════════════════


class TestGuardrailLeverageLimit:
    """Test leverage limit enforcement."""

    def test_exceeds_leverage_rejected(self) -> None:
        layer = GuardrailValidationLayer()
        # position=0.5, mid=100000, equity=1000 → projected_leverage=50 > max=3
        result = layer.validate(
            strategy=_strategy(max_leverage=3.0),
            market_context=_ctx(mid_price=100_000.0, current_position=0.5, equity_usd=1_000.0),
            plan=_plan(qty=0.1),
            risk=_risk_approved(qty=0.1),
            decision=_decision(action="BUY", quantity=0.1),
        )
        assert result.allowed is False
        assert "leverage_limit" in result.blocked_by


class TestGuardrailSymbolMismatch:
    """Test symbol constraint enforcement."""

    def test_symbol_mismatch_rejected(self) -> None:
        layer = GuardrailValidationLayer()
        result = layer.validate(
            strategy=_strategy(symbol="BTC/USDT"),
            market_context=_ctx(symbol="ETH/USDT"),
            plan=_plan(),
            risk=_risk_approved(),
            decision=_decision(),
        )
        assert result.allowed is False
        assert "symbol_constraint" in result.blocked_by
