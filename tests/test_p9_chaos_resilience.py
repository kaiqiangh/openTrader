from __future__ import annotations

from collections.abc import Mapping
import asyncio
import uuid

import pytest

from services.agent_orchestrator.memory_layer import AgentMemoryLayer, DecisionMemoryRecord
from services.llm_gateway.contracts import GatewaySettings, LLMRequest, ProviderSettings
from services.llm_gateway.gateway import LLMGateway
from services.market_ingestion.canonical_pipeline import CanonicalNormalizationPipeline
from services.market_ingestion.exchange_adapter import CCXTIngestionAdapter
from services.notification_service.publishers import NotificationEventBridge
from services.shared.runtime.broker import InMemoryTopicBroker
from services.simulation_execution.metrics_tracing import SimulationExecutionMetrics
from services.simulation_execution.worker import SimulationExecutionWorker
from services.workers.runtime_pipeline import MarketIngestionRuntimeWorker


def _build_mock_execution_intent() -> dict[str, object]:
    return {
        "trace_id": str(uuid.uuid4()),
        "decision_id": str(uuid.uuid4()),
        "mode": "MOCK",
        "idempotency_key": "execution.intent:mock:p9-chaos",
        "event_type": "execution.intent.created",
        "emitted_at": "2026-02-15T02:00:00Z",
        "payload": {
            "strategy_id": "chaos-suite",
            "symbol": "BTC/USDT",
            "action": "BUY",
            "quantity": 0.02,
            "market_context": {"mid_price": 42_000.0},
        },
        "service": "p9_chaos_suite",
    }


class _FailOnceBrokerProxy:
    def __init__(self, broker: InMemoryTopicBroker) -> None:
        self._broker = broker
        self._consume_failed = False

    async def publish(self, *, routing_key: str, message: dict[str, object]) -> object:
        return await self._broker.publish(routing_key=routing_key, message=message)

    async def consume(self, *, queue_name: str, timeout_seconds: float | None = None) -> dict[str, object] | None:
        if not self._consume_failed:
            self._consume_failed = True
            raise ConnectionError("simulated broker restart")
        return await self._broker.consume(queue_name=queue_name, timeout_seconds=timeout_seconds)


class _RestClient:
    async def fetch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, object]:
        _ = limit
        assert symbol == "BTC/USDT"
        return {
            "nonce": 900,
            "timestamp": 1739535600000,
            "bids": [[42000.0, 5.0], [41999.0, 2.0]],
            "asks": [[42001.0, 2.0], [42002.0, 1.0]],
        }


class _FailOnceWsClient:
    def __init__(self) -> None:
        self.failed = False

    async def watch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, object]:
        _ = limit
        assert symbol == "BTC/USDT"
        if not self.failed:
            self.failed = True
            raise TimeoutError("simulated exchange disconnect")
        return {
            "U": 901,
            "u": 902,
            "timestamp": 1739535601000,
            "bids": [[42000.0, 8.0], [41999.0, 2.0]],
            "asks": [[42001.0, 1.0], [42002.0, 0.5]],
        }


class _SlowProvider:
    async def complete(
        self,
        *,
        model: str,
        messages: tuple[Mapping[str, object], ...],
        request_kwargs: Mapping[str, object],
    ) -> Mapping[str, object]:
        _ = model, messages, request_kwargs
        await asyncio.sleep(0.08)
        return {"content": "slow", "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}}


class _FastProvider:
    async def complete(
        self,
        *,
        model: str,
        messages: tuple[Mapping[str, object], ...],
        request_kwargs: Mapping[str, object],
    ) -> Mapping[str, object]:
        _ = request_kwargs
        return {
            "content": f"fallback:{model}",
            "usage": {"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12},
        }


class _InMemoryShortTermStore:
    def __init__(self) -> None:
        self.slots: dict[str, dict[str, object]] = {}

    async def write_slot(
        self,
        *,
        mode: str,
        strategy_id: str,
        decision_id: str,
        slot: str,
        payload: Mapping[str, object],
        ttl_seconds: int,
    ) -> None:
        _ = mode, strategy_id, decision_id, ttl_seconds
        self.slots[slot] = dict(payload)

    async def read_slots(
        self,
        *,
        mode: str,
        strategy_id: str,
        decision_id: str,
    ) -> Mapping[str, Mapping[str, object]]:
        _ = mode, strategy_id, decision_id
        return dict(self.slots)


class _FailOnceLongTermStore:
    def __init__(self) -> None:
        self.persist_attempts = 0
        self.saved: DecisionMemoryRecord | None = None

    async def persist_decision_summary(self, record: DecisionMemoryRecord) -> None:
        self.persist_attempts += 1
        if self.persist_attempts == 1:
            raise ConnectionError("simulated database restart")
        self.saved = record

    async def read_decision_summary(self, *, decision_id: str) -> DecisionMemoryRecord | None:
        if self.saved is None:
            return None
        if self.saved.decision_id != decision_id:
            return None
        return self.saved


def _gateway_settings() -> GatewaySettings:
    return GatewaySettings(
        providers={
            "primary": ProviderSettings(alias="primary", model="gpt-4o-mini", timeout_ms=40, max_retries=1),
            "secondary": ProviderSettings(alias="secondary", model="gpt-4o-mini", timeout_ms=40, max_retries=0),
        },
        default_provider_order=("primary", "secondary"),
        retry_base_ms=1,
        retry_max_ms=2,
    )


def _llm_request() -> LLMRequest:
    return LLMRequest(
        trace_id="f2d6c79a-7c08-4d3e-a546-c89279c3bc28",
        decision_id="165f8cad-07b6-4f1c-9217-3e13f811f015",
        strategy_id="chaos-suite",
        agent_name="planner",
        messages=({"role": "system", "content": "plan"}, {"role": "user", "content": "buy or sell"}),
        temperature=0.2,
        max_tokens=128,
        metadata={"symbol": "BTC/USDT"},
    )


@pytest.mark.asyncio
async def test_p9_chaos_broker_restart_recovers_and_completes_dispatch() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    await broker.publish(routing_key="execution.intent.mock", message=_build_mock_execution_intent())

    metrics = SimulationExecutionMetrics()
    worker = SimulationExecutionWorker(
        broker=_FailOnceBrokerProxy(broker),
        metrics=metrics,
    )

    with pytest.raises(ConnectionError):
        await worker.run_once(timeout_seconds=0.0)

    recovered = await worker.run_once(timeout_seconds=0.0)
    assert recovered is not None
    assert recovered.status == "FILLED"

    snapshot = metrics.snapshot()["totals"]
    # Consume-stage broker failures happen before worker stage instrumentation.
    assert snapshot["failure_total"] == 0
    assert snapshot["success_total"] == 1


@pytest.mark.asyncio
async def test_p9_chaos_exchange_disconnect_emits_alert_then_recovers() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    worker = MarketIngestionRuntimeWorker(
        adapter=CCXTIngestionAdapter(
            exchange="binance",
            rest_client=_RestClient(),
            ws_client=_FailOnceWsClient(),
        ),
        pipeline=CanonicalNormalizationPipeline(publisher=broker),
        symbol="BTC/USDT",
        mode="MOCK",
        depth=20,
        notification_bridge=NotificationEventBridge(publisher=broker),
    )

    # First call: WS fails → worker falls back to REST (graceful degradation, no exception)
    fallback_envelope = await worker.run_once()
    assert fallback_envelope is not None

    # Second call: WS recovers → uses WS again
    recovered_envelope = await worker.run_once()
    assert recovered_envelope["event_type"] == "market.canonical.orderbook_delta"

    notification_event = await broker.consume(queue_name="notify.events.raw", timeout_seconds=0.0)
    assert notification_event is not None
    assert notification_event["event_type"] == "notify.system.event"
    assert notification_event["payload"]["source_event_type"] == "system.exchange.connectivity_issue"


@pytest.mark.asyncio
async def test_p9_chaos_llm_timeout_falls_back_to_secondary_provider() -> None:
    gateway = LLMGateway(
        settings=_gateway_settings(),
        provider_clients={"primary": _SlowProvider(), "secondary": _FastProvider()},
    )

    response = await gateway.generate(_llm_request())

    assert response.provider == "secondary"
    assert response.content.startswith("fallback:")
    assert response.usage["total_tokens"] == 12


@pytest.mark.asyncio
async def test_p9_chaos_db_restart_allows_retry_to_persist_summary() -> None:
    short_term_store = _InMemoryShortTermStore()
    long_term_store = _FailOnceLongTermStore()
    layer = AgentMemoryLayer(
        short_term_store=short_term_store,
        long_term_store=long_term_store,
    )

    with pytest.raises(ConnectionError):
        await layer.persist_decision_summary(
            trace_id="4af5eb95-2bdb-4a63-8a1a-3f749b02e8ff",
            decision_id="fda3e0ff-edf4-429d-9087-c3805f2b8b2f",
            strategy_id="chaos-suite",
            mode="REAL",
            status="RISK_APPROVED",
            market_context={"symbol": "BTC/USDT"},
            plan={"action": "BUY"},
            risk={"approved": True},
            execution_decision={"action": "BUY", "quantity": 0.02},
            guardrail={"allowed": True},
            lifecycle=({"event_type": "agent.decision.received"},),
        )

    record = await layer.persist_decision_summary(
        trace_id="4af5eb95-2bdb-4a63-8a1a-3f749b02e8ff",
        decision_id="fda3e0ff-edf4-429d-9087-c3805f2b8b2f",
        strategy_id="chaos-suite",
        mode="REAL",
        status="RISK_APPROVED",
        market_context={"symbol": "BTC/USDT"},
        plan={"action": "BUY"},
        risk={"approved": True},
        execution_decision={"action": "BUY", "quantity": 0.02},
        guardrail={"allowed": True},
        lifecycle=({"event_type": "agent.decision.received"},),
    )

    assert long_term_store.persist_attempts == 2
    assert long_term_store.saved is not None
    assert long_term_store.saved.decision_id == record.decision_id

    snapshot = await layer.read_decision_memory(
        mode="REAL",
        strategy_id="chaos-suite",
        decision_id=record.decision_id,
    )
    assert snapshot.slots["summary"]["status"] == "RISK_APPROVED"
