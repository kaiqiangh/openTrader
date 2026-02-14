from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from services.agent_orchestrator.contracts import StrategyConfig
from services.agent_orchestrator.orchestrator import AgentOrchestrator
from services.shared.contracts.message_envelope import EnvelopeValidationError


class _FakePublisher:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def publish(self, *, routing_key: str, message: dict[str, object]) -> None:
        self.messages.append({"routing_key": routing_key, "message": message})


def _market_event(*, mode: str = "MOCK") -> dict[str, object]:
    return {
        "trace_id": str(uuid.uuid4()),
        "decision_id": str(uuid.uuid4()),
        "mode": mode,
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


def _strategy(*, mode: str = "MOCK", max_notional: float = 20_000.0) -> StrategyConfig:
    return StrategyConfig(
        strategy_id="scalp-long-short",
        symbol="BTC/USDT",
        mode=mode,
        order_size=0.1,
        planner_buy_threshold=0.2,
        planner_sell_threshold=0.2,
        risk_max_notional_usd=max_notional,
        risk_max_position_size=1.0,
        risk_max_drawdown_pct=0.2,
        risk_min_confidence=0.2,
    )


@pytest.mark.asyncio
async def test_orchestrator_consumes_market_event_and_publishes_lifecycle_and_intent() -> None:
    publisher = _FakePublisher()
    orchestrator = AgentOrchestrator(publisher=publisher)

    result = await orchestrator.handle_market_event(_market_event(mode="MOCK"), strategy=_strategy())

    assert result.status == "RISK_APPROVED"
    assert [item["event_type"] for item in result.lifecycle] == [
        "agent.decision.received",
        "agent.decision.context_enriched",
        "agent.decision.planned",
        "agent.decision.risk_approved",
        "agent.decision.action_proposed",
        "agent.decision.intent_published",
    ]

    intent_messages = [item for item in publisher.messages if item["routing_key"] == "execution.intent.mock"]
    assert len(intent_messages) == 1
    intent_envelope = intent_messages[0]["message"]
    assert intent_envelope["payload"]["action"] in {"BUY", "SELL", "HOLD", "CLOSE"}
    assert intent_envelope["payload"]["symbol"] == "BTC/USDT"
    assert result.execution_decision is not None
    assert intent_envelope["payload"]["action"] == result.execution_decision.action
    assert intent_envelope["payload"]["quantity"] == result.execution_decision.quantity
    assert result.market_context.news["summary"].startswith("ETF inflow")
    assert result.market_context.context["microstructure_regime"] == "bid_dominant"
    assert result.execution_intent is not None


@pytest.mark.asyncio
async def test_orchestrator_marks_decision_rejected_when_risk_fails() -> None:
    publisher = _FakePublisher()
    orchestrator = AgentOrchestrator(publisher=publisher)

    result = await orchestrator.handle_market_event(
        _market_event(mode="MOCK"),
        strategy=_strategy(max_notional=500.0),
    )

    assert result.status == "RISK_REJECTED"
    assert "agent.decision.risk_rejected" in [item["event_type"] for item in result.lifecycle]
    assert "agent.decision.context_enriched" in [item["event_type"] for item in result.lifecycle]
    assert "agent.decision.action_proposed" in [item["event_type"] for item in result.lifecycle]
    assert result.execution_decision is not None
    assert result.execution_decision.action == "HOLD"
    intent_messages = [item for item in publisher.messages if item["routing_key"] == "execution.intent.mock"]
    assert intent_messages == []


@pytest.mark.asyncio
async def test_orchestrator_rejects_invalid_market_envelope() -> None:
    publisher = _FakePublisher()
    orchestrator = AgentOrchestrator(publisher=publisher)
    invalid_envelope = _market_event(mode="PAPER")

    with pytest.raises(EnvelopeValidationError):
        await orchestrator.handle_market_event(invalid_envelope, strategy=_strategy(mode="MOCK"))
