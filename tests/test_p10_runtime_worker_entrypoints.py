from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from services.shared.runtime.broker import InMemoryTopicBroker
from services.workers.main import RuntimeWorkerSettings, build_runtime_broker, build_runtime_worker


def _market_envelope(*, mode: str = "MOCK") -> dict[str, object]:
    return {
        "trace_id": str(uuid.uuid4()),
        "decision_id": str(uuid.uuid4()),
        "mode": mode,
        "idempotency_key": f"market.canonical:{mode}:{uuid.uuid4()}",
        "event_type": "market.canonical.orderbook_delta",
        "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "payload": {
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "timestamp_ms": 1739535600000,
            "sequence_start": 100,
            "sequence_end": 101,
            "bids": [{"price": 42000.0, "amount": 1.0}],
            "asks": [{"price": 42001.0, "amount": 1.0}],
        },
        "service": "market_ingestion",
    }


def _execution_intent_envelope(*, mode: str = "MOCK") -> dict[str, object]:
    return {
        "trace_id": str(uuid.uuid4()),
        "decision_id": str(uuid.uuid4()),
        "mode": mode,
        "idempotency_key": f"execution.intent:{mode}:{uuid.uuid4()}",
        "event_type": "execution.intent.created",
        "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "payload": {
            "strategy_id": "default-strategy",
            "symbol": "BTC/USDT",
            "action": "BUY",
            "quantity": 0.1,
            "confidence": 0.8,
            "rationale": ["test"],
            "constraints": {"schema_valid": True},
            "market_context": {
                "mid_price": 42000.0,
                "best_bid": 41999.5,
                "best_ask": 42000.5,
                "spread_bps": 0.24,
                "orderbook_imbalance": 0.1,
                "microstructure_regime": "balanced",
                "news_summary": "neutral",
                "news_sentiment": 0.0,
            },
        },
        "service": "agent_orchestrator",
    }


def _settings(*, worker: str) -> RuntimeWorkerSettings:
    return RuntimeWorkerSettings(
        worker=worker,
        broker_backend="inmemory",
        topology_path="config/rabbitmq/topology.json",
        mode="MOCK",
        symbol="BTC/USDT",
        strategy_id="default-strategy",
        once=True,
        validate_only=False,
        max_idle_cycles=1,
        poll_timeout_seconds=0.0,
        idle_sleep_seconds=0.0,
        bootstrap_topology=False,
        portfolio_base_balance_usd=100000.0,
    )


def test_build_runtime_broker_supports_inmemory_backend() -> None:
    broker = build_runtime_broker(backend="inmemory", topology_path="config/rabbitmq/topology.json")
    assert isinstance(broker, InMemoryTopicBroker)


@pytest.mark.asyncio
async def test_orchestrator_worker_runner_consumes_market_event_and_publishes_intent() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    build = build_runtime_worker(settings=_settings(worker="orchestrator"), broker=broker)
    await broker.publish(routing_key="market.canonical", message=_market_envelope())

    worked = await build.worker.run_once(timeout_seconds=0.0)

    assert worked is True
    assert broker.queue_size("market.canonical") == 0


@pytest.mark.asyncio
async def test_simulation_worker_runner_consumes_execution_intent_and_publishes_oms_events() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    build = build_runtime_worker(settings=_settings(worker="simulation"), broker=broker)
    await broker.publish(
        routing_key="execution.intent.mock",
        message=_execution_intent_envelope(),
    )

    worked = await build.worker.run_once(timeout_seconds=0.0)

    assert worked is True
    assert broker.queue_size("oms.events.order_updates") == 2


@pytest.mark.asyncio
async def test_news_worker_runner_generates_summary_artifact() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    build = build_runtime_worker(settings=_settings(worker="news"), broker=broker)

    worked = await build.worker.run_once(timeout_seconds=0.0)

    assert worked is True
