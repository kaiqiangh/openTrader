from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from services.shared.runtime.broker import InMemoryTopicBroker
from services.simulation_execution.metrics_tracing import SimulationExecutionMetrics
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
async def test_simulation_worker_records_success_metrics_and_trace_span() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    metrics = SimulationExecutionMetrics()
    worker = SimulationExecutionWorker(broker=broker, metrics=metrics)

    envelope = _intent_envelope(mode="MOCK", action="BUY", quantity=0.3)
    await broker.publish(routing_key="execution.intent.mock", message=envelope)

    result = await worker.run_once(timeout_seconds=0.0)

    assert result is not None
    assert result.status == "FILLED"

    snapshot = metrics.snapshot()
    assert snapshot["totals"]["runs_total"] == 1
    assert snapshot["totals"]["success_total"] == 1
    assert snapshot["totals"]["failure_total"] == 0
    assert snapshot["totals"]["events_published_total"] == 2
    assert snapshot["latency_ms"]["avg"] is not None

    spans = snapshot["recent_spans"]
    assert len(spans) == 1
    assert spans[0]["status"] == "succeeded"
    assert spans[0]["trace_id"] == envelope["trace_id"]
    assert spans[0]["decision_id"] == envelope["decision_id"]


@pytest.mark.asyncio
async def test_simulation_worker_records_failure_metrics_on_mode_leakage() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    metrics = SimulationExecutionMetrics()
    worker = SimulationExecutionWorker(broker=broker, metrics=metrics)

    await broker.publish(
        routing_key="execution.intent.mock",
        message=_intent_envelope(mode="REAL", action="BUY", quantity=0.2),
    )

    with pytest.raises(SimulationSafetyViolation):
        await worker.run_once(timeout_seconds=0.0)

    snapshot = metrics.snapshot()
    assert snapshot["totals"]["runs_total"] == 1
    assert snapshot["totals"]["success_total"] == 0
    assert snapshot["totals"]["failure_total"] == 1
    assert snapshot["totals"]["events_published_total"] == 0
    assert snapshot["latency_ms"]["avg"] is not None

    spans = snapshot["recent_spans"]
    assert len(spans) == 1
    assert spans[0]["status"] == "failed"
    assert spans[0]["error_type"] == "SimulationSafetyViolation"
