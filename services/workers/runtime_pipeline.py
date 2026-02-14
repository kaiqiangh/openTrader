from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.agent_orchestrator.contracts import OrchestrationResult, StrategyConfig
from services.agent_orchestrator.orchestrator import AgentOrchestrator
from services.market_ingestion.canonical_pipeline import CanonicalNormalizationPipeline
from services.market_ingestion.exchange_adapter import CCXTIngestionAdapter


@dataclass(frozen=True, slots=True)
class RuntimeCycleResult:
    market_envelope: dict[str, Any]
    orchestration: OrchestrationResult | None


class MarketIngestionRuntimeWorker:
    def __init__(
        self,
        *,
        adapter: CCXTIngestionAdapter,
        pipeline: CanonicalNormalizationPipeline,
        symbol: str,
        mode: str,
        depth: int = 200,
    ) -> None:
        self.adapter = adapter
        self.pipeline = pipeline
        self.symbol = symbol
        self.mode = mode
        self.depth = depth
        self._bootstrapped = False

    async def run_once(self) -> dict[str, Any]:
        if not self._bootstrapped:
            await self.adapter.bootstrap_snapshot(self.symbol, limit=self.depth)
            self._bootstrapped = True

        delta = await self.adapter.poll_delta(self.symbol, limit=self.depth)
        return await self.pipeline.publish_order_book_delta(delta, mode=self.mode)


class AgentOrchestratorRuntimeWorker:
    def __init__(
        self,
        *,
        broker_consumer: Any,
        orchestrator: AgentOrchestrator,
        queue_name: str = "market.canonical",
    ) -> None:
        self.broker_consumer = broker_consumer
        self.orchestrator = orchestrator
        self.queue_name = queue_name

    async def run_once(
        self,
        *,
        strategy: StrategyConfig,
        timeout_seconds: float | None = 0.0,
    ) -> OrchestrationResult | None:
        envelope = await self.broker_consumer.consume(
            queue_name=self.queue_name,
            timeout_seconds=timeout_seconds,
        )
        if envelope is None:
            return None
        return await self.orchestrator.handle_market_event(envelope, strategy=strategy)


class RuntimeIntegrationGate:
    def __init__(
        self,
        *,
        market_worker: MarketIngestionRuntimeWorker,
        orchestrator_worker: AgentOrchestratorRuntimeWorker,
        strategy: StrategyConfig,
    ) -> None:
        self.market_worker = market_worker
        self.orchestrator_worker = orchestrator_worker
        self.strategy = strategy

    async def run_cycle(self) -> RuntimeCycleResult:
        market_envelope = await self.market_worker.run_once()
        orchestration = await self.orchestrator_worker.run_once(
            strategy=self.strategy,
            timeout_seconds=0.0,
        )
        return RuntimeCycleResult(market_envelope=market_envelope, orchestration=orchestration)
