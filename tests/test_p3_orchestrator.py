from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from services.agent_orchestrator.contracts import StrategyConfig
from services.agent_orchestrator.metrics_tracing import AgentRuntimeMetrics
from services.agent_orchestrator.memory_layer import AgentMemoryLayer, DecisionMemoryRecord
from services.agent_orchestrator.orchestrator import AgentOrchestrator
from services.agent_orchestrator.planner_agent import PlannerAgent
from services.shared.contracts.message_envelope import EnvelopeValidationError


class _FakePublisher:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def publish(self, *, routing_key: str, message: dict[str, object]) -> None:
        self.messages.append({"routing_key": routing_key, "message": message})


class _FakeRedisMemoryStore:
    def __init__(self) -> None:
        self.read_calls: list[dict[str, str]] = []
        self.write_calls: list[dict[str, str]] = []

    async def read_slots(self, *, mode: str, strategy_id: str, decision_id: str) -> dict[str, object]:
        self.read_calls.append(
            {"mode": mode, "strategy_id": strategy_id, "decision_id": decision_id}
        )
        return {}

    async def write_slot(
        self,
        *,
        mode: str,
        strategy_id: str,
        decision_id: str,
        slot: str,
        payload: dict[str, object],
        ttl_seconds: int,
    ) -> None:
        self.write_calls.append(
            {
                "mode": mode,
                "strategy_id": strategy_id,
                "decision_id": decision_id,
                "slot": slot,
            }
        )


class _FakePostgresMemoryStore:
    def __init__(self) -> None:
        self.records: list[DecisionMemoryRecord] = []

    async def persist_decision_summary(self, record: DecisionMemoryRecord) -> None:
        self.records.append(record)

    async def read_decision_summary(self, *, decision_id: str) -> DecisionMemoryRecord | None:
        return None


class _FailingPlannerAgent(PlannerAgent):
    def build_plan(self, *, market_context: dict[str, object], strategy: StrategyConfig):  # type: ignore[override]
        _ = market_context, strategy
        raise RuntimeError("planner stage failed")


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


def _strategy(
    *,
    mode: str = "MOCK",
    max_notional: float = 20_000.0,
    symbol: str = "BTC/USDT",
) -> StrategyConfig:
    return StrategyConfig(
        strategy_id="scalp-long-short",
        symbol=symbol,
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
        "agent.decision.guardrail_passed",
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
    assert "agent.decision.guardrail_passed" in [item["event_type"] for item in result.lifecycle]
    assert result.execution_decision is not None
    assert result.execution_decision.action == "HOLD"
    intent_messages = [item for item in publisher.messages if item["routing_key"] == "execution.intent.mock"]
    assert intent_messages == []


@pytest.mark.asyncio
async def test_orchestrator_marks_guardrail_rejected_when_symbol_constraint_fails() -> None:
    publisher = _FakePublisher()
    orchestrator = AgentOrchestrator(publisher=publisher)

    result = await orchestrator.handle_market_event(
        _market_event(mode="MOCK"),
        strategy=_strategy(symbol="ETH/USDT"),
    )

    assert result.status == "GUARDRAIL_REJECTED"
    assert "agent.decision.guardrail_rejected" in [item["event_type"] for item in result.lifecycle]
    assert "symbol_constraint" in result.guardrail.blocked_by
    intent_messages = [item for item in publisher.messages if item["routing_key"] == "execution.intent.mock"]
    assert intent_messages == []


@pytest.mark.asyncio
async def test_orchestrator_rejects_invalid_market_envelope() -> None:
    publisher = _FakePublisher()
    orchestrator = AgentOrchestrator(publisher=publisher)
    invalid_envelope = _market_event(mode="PAPER")

    with pytest.raises(EnvelopeValidationError):
        await orchestrator.handle_market_event(invalid_envelope, strategy=_strategy(mode="MOCK"))


@pytest.mark.asyncio
async def test_orchestrator_persists_short_and_long_term_memory() -> None:
    publisher = _FakePublisher()
    redis_store = _FakeRedisMemoryStore()
    postgres_store = _FakePostgresMemoryStore()
    memory_layer = AgentMemoryLayer(short_term_store=redis_store, long_term_store=postgres_store)
    orchestrator = AgentOrchestrator(publisher=publisher, memory_layer=memory_layer)

    result = await orchestrator.handle_market_event(_market_event(mode="MOCK"), strategy=_strategy())

    assert redis_store.read_calls == [
        {
            "mode": "MOCK",
            "strategy_id": "scalp-long-short",
            "decision_id": result.decision_id,
        }
    ]
    written_slots = {call["slot"] for call in redis_store.write_calls}
    assert {
        "context",
        "plan",
        "risk",
        "execution_decision",
        "guardrail",
        "status",
        "summary",
    }.issubset(written_slots)
    assert len(postgres_store.records) == 1
    assert postgres_store.records[0].decision_id == result.decision_id
    assert postgres_store.records[0].status == result.status


@pytest.mark.asyncio
async def test_orchestrator_records_stage_latency_metrics() -> None:
    publisher = _FakePublisher()
    metrics = AgentRuntimeMetrics()
    orchestrator = AgentOrchestrator(publisher=publisher, metrics=metrics)

    await orchestrator.handle_market_event(_market_event(mode="MOCK"), strategy=_strategy())
    snapshot = metrics.snapshot()

    stage_names = set(snapshot["agent_stages"].keys())
    assert {"market_context_agent", "planner_agent", "risk_agent", "execution_decision_agent", "guardrail_validation"}.issubset(stage_names)
    assert snapshot["agent_stages"]["planner_agent"]["runs_total"] == 1
    assert snapshot["agent_stages"]["planner_agent"]["failures_total"] == 0


@pytest.mark.asyncio
async def test_orchestrator_records_failure_metric_when_stage_raises() -> None:
    publisher = _FakePublisher()
    metrics = AgentRuntimeMetrics()
    orchestrator = AgentOrchestrator(
        publisher=publisher,
        planner_agent=_FailingPlannerAgent(),
        metrics=metrics,
    )

    with pytest.raises(RuntimeError):
        await orchestrator.handle_market_event(_market_event(mode="MOCK"), strategy=_strategy())

    snapshot = metrics.snapshot()
    planner = snapshot["agent_stages"]["planner_agent"]
    assert planner["runs_total"] == 1
    assert planner["failures_total"] == 1
    assert planner["failure_rate"] == 1.0
