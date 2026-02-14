from __future__ import annotations

import pytest

from services.agent_orchestrator.contracts import StrategyConfig
from services.agent_orchestrator.orchestrator import AgentOrchestrator
from services.market_ingestion.canonical_pipeline import CanonicalNormalizationPipeline
from services.market_ingestion.exchange_adapter import CCXTIngestionAdapter
from services.shared.runtime.broker import InMemoryTopicBroker
from services.simulation_execution.worker import SimulationExecutionWorker
from services.workers.runtime_pipeline import (
    AgentOrchestratorRuntimeWorker,
    MarketIngestionRuntimeWorker,
    RuntimeIntegrationGate,
)


class _TrackedExchangeClient:
    def __init__(self) -> None:
        self.fetch_calls = 0
        self.watch_calls = 0
        self.order_write_calls = 0

    async def fetch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, object]:
        _ = limit
        self.fetch_calls += 1
        assert symbol == "BTC/USDT"
        return {
            "nonce": 500,
            "timestamp": 1739535600000,
            "bids": [[42000.0, 5.0], [41999.0, 2.0]],
            "asks": [[42001.0, 2.0], [42002.0, 1.0]],
        }

    async def watch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, object]:
        _ = limit
        self.watch_calls += 1
        assert symbol == "BTC/USDT"
        return {
            "U": 501,
            "u": 502,
            "timestamp": 1739535601000,
            "bids": [[42000.0, 8.0], [41999.0, 2.0]],
            "asks": [[42001.0, 1.0], [42002.0, 0.5]],
        }

    async def create_order(self, *_: object, **__: object) -> dict[str, object]:
        self.order_write_calls += 1
        raise AssertionError("MOCK pipeline must never call live order create endpoint")

    async def cancel_order(self, *_: object, **__: object) -> dict[str, object]:
        self.order_write_calls += 1
        raise AssertionError("MOCK pipeline must never call live order cancel endpoint")


def _strategy() -> StrategyConfig:
    return StrategyConfig(
        strategy_id="scalp-long-short-mock-isolation",
        symbol="BTC/USDT",
        mode="MOCK",
        order_size=0.1,
        planner_buy_threshold=0.2,
        planner_sell_threshold=0.2,
        risk_max_notional_usd=50_000.0,
        risk_max_position_size=1.0,
        risk_max_drawdown_pct=0.3,
        risk_min_confidence=0.2,
    )


@pytest.mark.asyncio
async def test_p9_mock_mode_never_uses_live_order_endpoints_or_real_queue() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    exchange_client = _TrackedExchangeClient()

    market_worker = MarketIngestionRuntimeWorker(
        adapter=CCXTIngestionAdapter(
            exchange="binance",
            rest_client=exchange_client,
            ws_client=exchange_client,
        ),
        pipeline=CanonicalNormalizationPipeline(publisher=broker),
        symbol="BTC/USDT",
        mode="MOCK",
        depth=20,
    )
    orchestrator_worker = AgentOrchestratorRuntimeWorker(
        broker_consumer=broker,
        orchestrator=AgentOrchestrator(publisher=broker),
    )
    gate = RuntimeIntegrationGate(
        market_worker=market_worker,
        orchestrator_worker=orchestrator_worker,
        strategy=_strategy(),
    )

    cycle = await gate.run_cycle()
    assert cycle.orchestration is not None
    assert cycle.orchestration.execution_intent is not None
    assert cycle.orchestration.execution_intent["mode"] == "MOCK"

    worker = SimulationExecutionWorker(broker=broker)
    simulation_result = await worker.run_once(timeout_seconds=0.0)
    assert simulation_result is not None
    assert simulation_result.status == "FILLED"

    assert exchange_client.fetch_calls == 1
    assert exchange_client.watch_calls == 1
    assert exchange_client.order_write_calls == 0
    assert broker.queue_size("execution.intent.real") == 0
    assert broker.queue_size("oms.events.order_updates") == 2
