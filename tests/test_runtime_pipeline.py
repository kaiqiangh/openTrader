from __future__ import annotations

import pytest

from services.agent_orchestrator.contracts import StrategyConfig
from services.agent_orchestrator.orchestrator import AgentOrchestrator
from services.market_ingestion.canonical_pipeline import CanonicalNormalizationPipeline
from services.market_ingestion.exchange_adapter import CCXTIngestionAdapter
from services.shared.runtime.broker import InMemoryTopicBroker
from services.workers.runtime_pipeline import (
    AgentOrchestratorRuntimeWorker,
    MarketIngestionRuntimeWorker,
    RuntimeIntegrationGate,
)


class _ScriptedRestClient:
    async def fetch_order_book(self, symbol: str, limit: int | None = None) -> dict:
        _ = limit
        assert symbol == "BTC/USDT"
        return {
            "nonce": 200,
            "timestamp": 1739535600000,
            "bids": [[42000.0, 5.0], [41999.0, 2.0]],
            "asks": [[42001.0, 2.0], [42002.0, 1.0]],
        }


class _ScriptedWsClient:
    async def watch_order_book(self, symbol: str, limit: int | None = None) -> dict:
        _ = limit
        assert symbol == "BTC/USDT"
        return {
            "U": 201,
            "u": 202,
            "timestamp": 1739535601000,
            "bids": [[42000.0, 8.0], [41999.0, 2.0]],
            "asks": [[42001.0, 1.0], [42002.0, 0.5]],
        }


def _strategy() -> StrategyConfig:
    return StrategyConfig(
        strategy_id="scalp-long-short",
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
async def test_runtime_pipeline_moves_market_event_to_execution_intent() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")

    adapter = CCXTIngestionAdapter(
        exchange="binance",
        rest_client=_ScriptedRestClient(),
        ws_client=_ScriptedWsClient(),
    )
    market_pipeline = CanonicalNormalizationPipeline(publisher=broker)
    market_worker = MarketIngestionRuntimeWorker(
        adapter=adapter,
        pipeline=market_pipeline,
        symbol="BTC/USDT",
        mode="MOCK",
        depth=20,
    )

    orchestrator = AgentOrchestrator(publisher=broker)
    orchestrator_worker = AgentOrchestratorRuntimeWorker(
        broker_consumer=broker,
        orchestrator=orchestrator,
    )

    gate = RuntimeIntegrationGate(
        market_worker=market_worker,
        orchestrator_worker=orchestrator_worker,
        strategy=_strategy(),
    )

    cycle = await gate.run_cycle()

    assert cycle.market_envelope["event_type"] == "market.canonical.orderbook_delta"
    assert cycle.orchestration is not None
    assert cycle.orchestration.status == "RISK_APPROVED"

    assert broker.queue_size("execution.intent.mock") == 1
    intent = await broker.consume(queue_name="execution.intent.mock", timeout_seconds=0.0)
    assert intent is not None
    assert intent["event_type"] == "execution.intent.created"
    assert intent["mode"] == "MOCK"
    assert intent["payload"]["symbol"] == "BTC/USDT"
