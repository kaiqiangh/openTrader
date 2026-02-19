from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import uuid

import pytest

from services.shared.runtime.broker import InMemoryTopicBroker
from services.workers.execution_lifecycle import (
    ExecutionLifecycleWorker,
    LifecycleStatusSnapshot,
)


class _ScriptedPrivateConnector:
    def __init__(self, *, scripted_batches: tuple[tuple[LifecycleStatusSnapshot, ...], ...]) -> None:
        self._batches = deque(scripted_batches)

    @property
    def supports_private_stream(self) -> bool:
        return True

    async def poll_updates(
        self,
        *,
        tracked_orders: tuple[object, ...],
        timeout_seconds: float,
    ) -> tuple[LifecycleStatusSnapshot, ...]:
        _ = tracked_orders, timeout_seconds
        if not self._batches:
            return ()
        return self._batches.popleft()


class _ScriptedStatusPoller:
    def __init__(self, *, scripted: tuple[LifecycleStatusSnapshot | None, ...]) -> None:
        self._responses = deque(scripted)

    async def fetch_status(self, *, order: object) -> LifecycleStatusSnapshot | None:
        _ = order
        if not self._responses:
            return None
        return self._responses.popleft()


def _execution_intent_envelope() -> dict[str, object]:
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "trace_id": str(uuid.uuid4()),
        "decision_id": str(uuid.uuid4()),
        "mode": "REAL",
        "idempotency_key": f"execution.intent.real:{uuid.uuid4()}",
        "event_type": "execution.intent.created",
        "emitted_at": now_iso,
        "payload": {
            "strategy_id": "phase2-strategy",
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "action": "BUY",
            "order_type": "MARKET",
            "time_in_force": None,
            "limit_price": None,
            "trigger_price": None,
            "reduce_only": False,
            "quantity": 0.1,
            "client_order_id": "client-phase2-001",
        },
        "service": "agent_orchestrator",
    }


@pytest.mark.asyncio
async def test_lifecycle_worker_publishes_delta_fills_from_private_stream() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    private_connector = _ScriptedPrivateConnector(
        scripted_batches=(
            (
                LifecycleStatusSnapshot(
                    exchange="binance",
                    symbol="BTC/USDT",
                    status="partially_filled",
                    exchange_order_id="binance-order-1",
                    client_order_id="client-phase2-001",
                    filled_quantity_total=0.04,
                    average_price=42010.0,
                    fee_total=0.10,
                    raw_response={},
                ),
            ),
            (
                LifecycleStatusSnapshot(
                    exchange="binance",
                    symbol="BTC/USDT",
                    status="filled",
                    exchange_order_id="binance-order-1",
                    client_order_id="client-phase2-001",
                    filled_quantity_total=0.1,
                    average_price=42020.0,
                    fee_total=0.25,
                    raw_response={},
                ),
            ),
        )
    )
    worker = ExecutionLifecycleWorker(
        broker=broker,
        private_stream_connector=private_connector,
        status_poller=_ScriptedStatusPoller(scripted=()),
        stream_stale_after_seconds=60.0,
        fallback_poll_interval_seconds=60.0,
    )

    await broker.publish(routing_key="execution.intent.real", message=_execution_intent_envelope())

    worked_first = await worker.run_once(timeout_seconds=0.0)
    events_first = await broker.drain("oms.events.order_updates")

    assert worked_first is True
    assert len(events_first) == 1
    first_event = events_first[0]
    assert first_event["event_type"] == "oms.order.partially_filled"
    first_payload = first_event["payload"]
    assert first_payload["quantity"] == pytest.approx(0.04)
    assert first_payload["exchange_order_id"] == "binance-order-1"

    worked_second = await worker.run_once(timeout_seconds=0.0)
    events_second = await broker.drain("oms.events.order_updates")

    assert worked_second is True
    assert len(events_second) == 1
    second_event = events_second[0]
    assert second_event["event_type"] == "oms.order.filled"
    second_payload = second_event["payload"]
    assert second_payload["quantity"] == pytest.approx(0.06)


@pytest.mark.asyncio
async def test_lifecycle_worker_uses_rest_fallback_when_private_stream_is_stale() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    private_connector = _ScriptedPrivateConnector(scripted_batches=((),))
    status_poller = _ScriptedStatusPoller(
        scripted=(
            LifecycleStatusSnapshot(
                exchange="binance",
                symbol="BTC/USDT",
                status="filled",
                exchange_order_id="binance-order-2",
                client_order_id="client-phase2-001",
                filled_quantity_total=0.1,
                average_price=42100.0,
                fee_total=0.2,
                raw_response={},
            ),
        )
    )
    worker = ExecutionLifecycleWorker(
        broker=broker,
        private_stream_connector=private_connector,
        status_poller=status_poller,
        stream_stale_after_seconds=0.0,
        fallback_poll_interval_seconds=0.0,
    )

    await broker.publish(routing_key="execution.intent.real", message=_execution_intent_envelope())

    worked = await worker.run_once(timeout_seconds=0.0)
    events = await broker.drain("oms.events.order_updates")

    assert worked is True
    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "oms.order.filled"
    payload = event["payload"]
    assert payload["source"] == "rest_fallback"
    assert payload["quantity"] == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_lifecycle_worker_suppresses_duplicate_terminal_snapshots() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    private_connector = _ScriptedPrivateConnector(scripted_batches=((), ()))
    status_snapshot = LifecycleStatusSnapshot(
        exchange="binance",
        symbol="BTC/USDT",
        status="filled",
        exchange_order_id="binance-order-3",
        client_order_id="client-phase2-001",
        filled_quantity_total=0.1,
        average_price=42150.0,
        fee_total=0.2,
        raw_response={},
    )
    status_poller = _ScriptedStatusPoller(scripted=(status_snapshot, status_snapshot))
    worker = ExecutionLifecycleWorker(
        broker=broker,
        private_stream_connector=private_connector,
        status_poller=status_poller,
        stream_stale_after_seconds=0.0,
        fallback_poll_interval_seconds=0.0,
    )

    await broker.publish(routing_key="execution.intent.real", message=_execution_intent_envelope())

    first_worked = await worker.run_once(timeout_seconds=0.0)
    first_events = await broker.drain("oms.events.order_updates")
    second_worked = await worker.run_once(timeout_seconds=0.0)
    second_events = await broker.drain("oms.events.order_updates")

    assert first_worked is True
    assert len(first_events) == 1
    assert first_events[0]["event_type"] == "oms.order.filled"
    assert second_worked is False
    assert second_events == []
