from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from services.agent_orchestrator.contracts import StrategyConfig
from services.agent_orchestrator.llm_runtime import (
    ExecutionSuggestion,
    PlannerSuggestion,
    RiskSuggestion,
)
from services.agent_orchestrator.orchestrator import AgentOrchestrator


class _FakePublisher:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def publish(self, *, routing_key: str, message: dict[str, object]) -> None:
        self.messages.append({"routing_key": routing_key, "message": message})


class _FakeLLMRuntime:
    def __init__(self) -> None:
        self.plan_calls = 0
        self.risk_calls = 0
        self.execution_calls = 0

    async def suggest_plan(self, **kwargs) -> PlannerSuggestion:  # noqa: ANN003
        _ = kwargs
        self.plan_calls += 1
        return PlannerSuggestion(
            action="BUY",
            confidence=0.91,
            target_quantity=0.12,
            rationale=("llm_plan",),
            metadata={"provider": "openai", "model": "gpt-5-mini"},
        )

    async def suggest_risk(self, **kwargs) -> RiskSuggestion:  # noqa: ANN003
        _ = kwargs
        self.risk_calls += 1
        return RiskSuggestion(
            approved=True,
            approved_quantity=0.12,
            risk_score=0.02,
            blocked_by=(),
            rationale=("llm_risk",),
            metadata={"provider": "openai", "model": "gpt-5-mini"},
        )

    async def suggest_execution(self, **kwargs) -> ExecutionSuggestion:  # noqa: ANN003
        _ = kwargs
        self.execution_calls += 1
        return ExecutionSuggestion(
            action="BUY",
            quantity=0.12,
            confidence=0.88,
            constraints={
                "order_type": "LIMIT",
                "time_in_force": "GTC",
                "limit_price": 42000.5,
            },
            rationale=("llm_exec",),
            metadata={"provider": "anthropic", "model": "claude-sonnet"},
        )


def _market_event() -> dict[str, object]:
    return {
        "trace_id": str(uuid.uuid4()),
        "decision_id": str(uuid.uuid4()),
        "mode": "MOCK",
        "idempotency_key": f"market.canonical.orderbook_delta:{uuid.uuid4()}",
        "event_type": "market.canonical.orderbook_delta",
        "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "payload": {
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "timestamp_ms": 1_739_535_602_000,
            "bids": [{"price": 42_000.0, "amount": 4.0}],
            "asks": [{"price": 42_001.0, "amount": 1.0}],
            "current_position": 0.1,
            "drawdown_pct": 0.01,
            "news": {
                "summary": "ETF inflow acceleration reported",
                "sentiment": 0.65,
                "source_count": 5,
            },
        },
    }


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


@pytest.mark.asyncio
async def test_orchestrator_applies_llm_runtime_suggestions_and_intent_fields() -> None:
    publisher = _FakePublisher()
    llm_runtime = _FakeLLMRuntime()
    orchestrator = AgentOrchestrator(publisher=publisher, llm_runtime=llm_runtime)

    result = await orchestrator.handle_market_event(_market_event(), strategy=_strategy())

    assert llm_runtime.plan_calls == 1
    assert llm_runtime.risk_calls == 1
    assert llm_runtime.execution_calls == 1

    assert result.plan.target_quantity == 0.12
    assert "llm_plan" in result.plan.rationale
    assert result.risk.approved is True
    assert "llm_risk" in result.risk.rationale
    assert result.execution_decision.quantity == 0.12
    assert "llm_exec" in result.execution_decision.rationale

    assert result.execution_intent is not None
    payload = result.execution_intent["payload"]
    assert payload["exchange"] == "binance"
    assert payload["order_type"] == "LIMIT"
    assert payload["time_in_force"] == "GTC"
    assert payload["limit_price"] == 42000.5
    assert payload["client_order_id"].startswith("scalp-long-short-")
