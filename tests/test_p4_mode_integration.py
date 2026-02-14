from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from services.shared.runtime.broker import InMemoryTopicBroker
from services.simulation_execution.safety_guard import SimulationSafetyViolation
from services.simulation_execution.worker import SimulationExecutionWorker


def _intent_envelope(*, mode: str = "MOCK", action: str = "BUY", quantity: float = 0.2) -> dict[str, object]:
    return {
        "trace_id": str(uuid.uuid4()),
        "decision_id": str(uuid.uuid4()),
        "mode": mode,
        "idempotency_key": f"execution.intent:{mode.lower()}:{uuid.uuid4()}",
        "event_type": "execution.intent.created",
        "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "payload": {
            "strategy_id": "scalp-long-short",
            "symbol": "BTC/USDT",
            "action": action,
            "quantity": quantity,
            "market_context": {"mid_price": 42000.0},
        },
    }


@pytest.mark.asyncio
async def test_mock_worker_processes_only_mock_queue() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    worker = SimulationExecutionWorker(broker=broker)

    await broker.publish(
        routing_key="execution.intent.real",
        message=_intent_envelope(mode="REAL", action="BUY", quantity=0.2),
    )

    result = await worker.run_once(timeout_seconds=0.0)

    assert result is None
    assert broker.queue_size("execution.intent.real") == 1
    assert broker.queue_size("oms.events.order_updates") == 0


@pytest.mark.asyncio
async def test_mock_worker_emits_created_and_filled_events_for_buy() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    worker = SimulationExecutionWorker(broker=broker)

    await broker.publish(
        routing_key="execution.intent.mock",
        message=_intent_envelope(mode="MOCK", action="BUY", quantity=0.25),
    )

    result = await worker.run_once(timeout_seconds=0.0)

    assert result is not None
    events = await broker.drain("oms.events.order_updates")
    assert [event["event_type"] for event in events] == ["oms.order.created", "oms.order.filled"]
    assert all(event["mode"] == "MOCK" for event in events)


@pytest.mark.asyncio
async def test_mock_worker_emits_ignored_event_for_hold() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    worker = SimulationExecutionWorker(broker=broker)

    await broker.publish(
        routing_key="execution.intent.mock",
        message=_intent_envelope(mode="MOCK", action="HOLD", quantity=0.0),
    )

    result = await worker.run_once(timeout_seconds=0.0)

    assert result is not None
    assert result.status == "IGNORED"
    events = await broker.drain("oms.events.order_updates")
    assert len(events) == 1
    assert events[0]["event_type"] == "oms.order.ignored"
    assert events[0]["payload"]["status"] == "IGNORED"


@pytest.mark.asyncio
async def test_mock_worker_rejects_mode_leakage_on_mock_queue() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    worker = SimulationExecutionWorker(broker=broker)

    await broker.publish(
        routing_key="execution.intent.mock",
        message=_intent_envelope(mode="REAL", action="BUY", quantity=0.1),
    )

    with pytest.raises(SimulationSafetyViolation):
        await worker.run_once(timeout_seconds=0.0)

    assert broker.queue_size("oms.events.order_updates") == 0
