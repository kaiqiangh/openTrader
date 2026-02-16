from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
import time
import uuid

from services.agent_orchestrator.contracts import OrchestrationResult, StrategyConfig
from services.agent_orchestrator.orchestrator import AgentOrchestrator
from services.market_ingestion.canonical_pipeline import CanonicalNormalizationPipeline
from services.market_ingestion.exchange_adapter import CCXTIngestionAdapter
from services.notification_service.publishers import NotificationEventBridge


@dataclass(frozen=True, slots=True)
class RuntimeCycleResult:
    market_envelope: dict[str, Any]
    orchestration: OrchestrationResult | None


class RuntimeMarketStateStore(Protocol):
    async def persist_orderbook_envelope(self, envelope: Mapping[str, Any]) -> None: ...


class RuntimeMarketTimeseriesStore(RuntimeMarketStateStore, Protocol):
    async def persist_kline_rows(
        self,
        *,
        exchange: str,
        symbol: str,
        interval: str,
        bars: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
    ) -> None: ...


class RuntimeKlineClient(Protocol):
    async def fetch_klines(
        self,
        symbol: str,
        *,
        interval: str,
        limit: int = 200,
    ) -> tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]]: ...


class MarketRuntimeWorker(Protocol):
    async def run_once(self) -> dict[str, Any]: ...


class MarketIngestionRuntimeWorker:
    def __init__(
        self,
        *,
        adapter: CCXTIngestionAdapter,
        pipeline: CanonicalNormalizationPipeline,
        symbol: str,
        mode: str,
        depth: int = 200,
        notification_bridge: NotificationEventBridge | None = None,
        state_store: RuntimeMarketStateStore | None = None,
        kline_client: RuntimeKlineClient | None = None,
        kline_intervals: tuple[str, ...] = (),
        kline_poll_interval_seconds: float = 60.0,
        kline_fetch_limit: int = 200,
    ) -> None:
        self.adapter = adapter
        self.pipeline = pipeline
        self.symbol = symbol
        self.mode = mode
        self.depth = depth
        self.notification_bridge = notification_bridge
        self.state_store = state_store
        self.kline_client = kline_client
        self.kline_intervals = tuple(
            interval.strip() for interval in kline_intervals if interval is not None and interval.strip()
        )
        self.kline_poll_interval_seconds = max(1.0, float(kline_poll_interval_seconds))
        self.kline_fetch_limit = max(1, int(kline_fetch_limit))
        self._bootstrapped = False
        self._last_kline_poll_monotonic: float | None = None

    async def run_once(self) -> dict[str, Any]:
        try:
            if not self._bootstrapped:
                await self.adapter.bootstrap_snapshot(self.symbol, limit=self.depth)
                self._bootstrapped = True

            delta = await self.adapter.poll_delta(self.symbol, limit=self.depth)
            envelope = await self.pipeline.publish_order_book_delta(delta, mode=self.mode)
            if self.state_store is not None:
                await self.state_store.persist_orderbook_envelope(envelope)
            await self._poll_klines_if_due()
            return envelope
        except Exception as exc:  # noqa: BLE001 - runtime worker preserves failure propagation
            if self.notification_bridge is not None:
                await self.notification_bridge.publish_system_health_event(
                    trace_id=str(uuid.uuid4()),
                    mode=self.mode,
                    event_type="system.exchange.connectivity_issue",
                    severity="CRITICAL",
                    reason=exc.__class__.__name__,
                    details={"symbol": self.symbol, "error": str(exc)},
                )
            raise

    async def _poll_klines_if_due(self) -> None:
        if self.kline_client is None or not self.kline_intervals:
            return
        if self.state_store is None:
            return

        persist_kline_rows = getattr(self.state_store, "persist_kline_rows", None)
        if persist_kline_rows is None:
            return

        now_monotonic = time.monotonic()
        if self._last_kline_poll_monotonic is not None:
            elapsed = now_monotonic - self._last_kline_poll_monotonic
            if elapsed < self.kline_poll_interval_seconds:
                return

        for interval in self.kline_intervals:
            bars = await self.kline_client.fetch_klines(
                self.symbol,
                interval=interval,
                limit=self.kline_fetch_limit,
            )
            await persist_kline_rows(
                exchange=self.adapter.exchange,
                symbol=self.symbol,
                interval=interval,
                bars=tuple(bars),
            )
        self._last_kline_poll_monotonic = now_monotonic


class MultiExchangeMarketIngestionRuntimeWorker:
    """Wrapper that runs multiple market ingestion workers in a single runtime process."""

    def __init__(self, *, workers: Sequence[MarketIngestionRuntimeWorker]) -> None:
        if not workers:
            raise ValueError("workers must be non-empty")
        self.workers = tuple(workers)
        # Backward-compatible field used by existing tests.
        self.adapter = self.workers[0].adapter

    async def run_once(self) -> dict[str, Any]:
        last_envelope: dict[str, Any] | None = None
        for worker in self.workers:
            last_envelope = await worker.run_once()
        if last_envelope is None:
            raise RuntimeError("multi-exchange market worker executed with no workers")
        return last_envelope


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
        self.last_envelope: Mapping[str, Any] | None = None

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
            self.last_envelope = None
            return None
        self.last_envelope = envelope
        return await self.orchestrator.handle_market_event(envelope, strategy=strategy)


class RuntimeIntegrationGate:
    def __init__(
        self,
        *,
        market_worker: MarketRuntimeWorker,
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
