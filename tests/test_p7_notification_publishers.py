from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from services.agent_orchestrator.contracts import StrategyConfig
from services.agent_orchestrator.orchestrator import AgentOrchestrator
from services.notification_service.publishers import NotificationEventBridge
from services.oms.risk_observability import RiskObservabilityCollector
from services.shared.runtime.broker import InMemoryTopicBroker
from services.simulation_execution.worker import SimulationExecutionWorker


class _CapturePublisher:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def publish(self, *, routing_key: str, message: dict[str, object]) -> None:
        self.messages.append({"routing_key": routing_key, "message": message})


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
            "current_position": 0.0,
            "drawdown_pct": 0.01,
            "news": {"summary": "ETF inflow", "sentiment": 0.4, "source_count": 2},
        },
    }


def _strategy() -> StrategyConfig:
    return StrategyConfig(
        strategy_id="btc-momentum",
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


def _intent_envelope() -> dict[str, object]:
    return {
        "trace_id": str(uuid.uuid4()),
        "decision_id": str(uuid.uuid4()),
        "mode": "MOCK",
        "idempotency_key": f"execution.intent:mock:{uuid.uuid4()}",
        "event_type": "execution.intent.created",
        "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "payload": {
            "strategy_id": "btc-momentum",
            "symbol": "BTC/USDT",
            "action": "BUY",
            "quantity": 0.2,
            "market_context": {"mid_price": 42_000.0},
        },
    }


@pytest.mark.asyncio
async def test_notification_bridge_publishes_from_strategy_and_oms_events() -> None:
    publisher = _CapturePublisher()
    bridge = NotificationEventBridge(publisher=publisher)

    await bridge.publish_strategy_event(
        {
            "trace_id": str(uuid.uuid4()),
            "decision_id": str(uuid.uuid4()),
            "mode": "MOCK",
            "idempotency_key": "agent.decision.intent_published:test",
            "event_type": "agent.decision.intent_published",
            "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "payload": {"strategy_id": "btc-momentum", "symbol": "BTC/USDT", "action": "BUY"},
            "service": "agent_orchestrator",
        }
    )
    await bridge.publish_oms_event(
        {
            "trace_id": str(uuid.uuid4()),
            "decision_id": str(uuid.uuid4()),
            "mode": "MOCK",
            "idempotency_key": "oms.order.filled:test",
            "event_type": "oms.order.filled",
            "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "payload": {"order_id": "order-1", "symbol": "BTC/USDT", "status": "FILLED"},
            "service": "simulation_execution",
        }
    )
    await bridge.publish_system_health_event(
        trace_id=str(uuid.uuid4()),
        mode="REAL",
        event_type="system.exchange.connectivity_issue",
        severity="CRITICAL",
        reason="websocket_disconnected",
        details={"exchange": "binance"},
    )

    assert len(publisher.messages) == 3
    assert all(item["routing_key"] == "notify.events.raw" for item in publisher.messages)


@pytest.mark.asyncio
async def test_orchestrator_and_simulation_worker_emit_notification_events_when_bridge_attached() -> (
    None
):
    capture = _CapturePublisher()
    bridge = NotificationEventBridge(publisher=capture)

    orchestrator = AgentOrchestrator(publisher=capture, notification_bridge=bridge)
    await orchestrator.handle_market_event(_market_event(), strategy=_strategy())

    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    worker = SimulationExecutionWorker(broker=broker, notification_bridge=bridge)
    await broker.publish(routing_key="execution.intent.mock", message=_intent_envelope())
    result = await worker.run_once(timeout_seconds=0.0)

    assert result is not None
    notify_events = [
        item for item in capture.messages if item["routing_key"] == "notify.events.raw"
    ]
    assert len(notify_events) >= 2


def test_risk_observability_emits_notification_events() -> None:
    collector = RiskObservabilityCollector()
    collector.record_control_events(
        events=(
            type(
                "RiskControlEvent",
                (),
                {
                    "event_type": "risk.kill_switch.enabled",
                    "control": "kill_switch",
                    "status": "enabled",
                    "reason": "manual",
                    "actor": "ops",
                    "metadata": {},
                    "occurred_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                },
            )(),
        )
    )

    notification_events = collector.drain_notification_events(mode="REAL")
    assert len(notification_events) == 1
    assert notification_events[0]["event_type"] == "notify.risk.event"
