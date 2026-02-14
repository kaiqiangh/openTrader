from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from services.shared.runtime.broker import InMemoryTopicBroker
from services.simulation_execution.engine import SimulationExecutionEngine, SimulationExecutionError
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


def test_simulation_engine_executes_buy_with_slippage_and_fee() -> None:
    engine = SimulationExecutionEngine(slippage_bps=2.0, fee_bps=5.0)

    result = engine.execute_intent(_intent_envelope(action="BUY", quantity=0.4))

    assert result.status == "FILLED"
    assert result.action == "BUY"
    assert result.quantity == 0.4
    assert result.fill_price > 42000.0
    assert result.fee_paid > 0
    assert len(result.events) == 2
    assert result.events[0]["event_type"] == "oms.order.created"
    assert result.events[1]["event_type"] == "oms.order.filled"


def test_simulation_engine_ignores_hold_action() -> None:
    engine = SimulationExecutionEngine()

    result = engine.execute_intent(_intent_envelope(action="HOLD", quantity=0.0))

    assert result.status == "IGNORED"
    assert len(result.events) == 1
    assert result.events[0]["event_type"] == "oms.order.ignored"


def test_simulation_engine_rejects_non_mock_mode() -> None:
    engine = SimulationExecutionEngine()

    with pytest.raises(SimulationExecutionError):
        engine.execute_intent(_intent_envelope(mode="REAL"))


@pytest.mark.asyncio
async def test_simulation_worker_consumes_mock_intent_and_publishes_oms_events() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    worker = SimulationExecutionWorker(broker=broker)

    await broker.publish(routing_key="execution.intent.mock", message=_intent_envelope())
    result = await worker.run_once(timeout_seconds=0.0)

    assert result is not None
    assert result.status == "FILLED"
    assert broker.queue_size("oms.events.order_updates") == 2
