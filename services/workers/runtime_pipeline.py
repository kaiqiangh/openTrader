from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
import time
import uuid

from services.agent_orchestrator.contracts import OrchestrationResult, StrategyConfig
from services.agent_orchestrator.orchestrator import AgentOrchestrator
from services.market_ingestion.canonical_pipeline import CanonicalNormalizationPipeline
from services.market_ingestion.connection_resilience import (
    BackoffConfig,
    ConnectionResilienceManager,
)
from services.market_ingestion.contracts import OrderBookDelta, OrderBookSnapshot
from services.market_ingestion.exchange_adapter import CCXTIngestionAdapter
from services.market_ingestion.gap_detection import GapDetectionModule
from services.market_ingestion.order_book_sync import OrderBookSequenceGapError, OrderBookSyncEngine
from services.market_ingestion.pipeline_metrics import MarketPipelineMetrics
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
        ws_stale_after_seconds: float = 15.0,
        ws_probe_interval_seconds: float = 5.0,
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
            interval.strip()
            for interval in kline_intervals
            if interval is not None and interval.strip()
        )
        self.kline_poll_interval_seconds = max(1.0, float(kline_poll_interval_seconds))
        self.kline_fetch_limit = max(1, int(kline_fetch_limit))
        self.ws_stale_after_seconds = max(0.0, float(ws_stale_after_seconds))
        self.ws_probe_interval_seconds = max(0.1, float(ws_probe_interval_seconds))
        self._bootstrapped = False
        self._last_kline_poll_monotonic: float | None = None
        self._next_ws_probe_monotonic = 0.0
        self._last_delta_source: str | None = None
        self._last_fallback_reason: str | None = None
        self._last_envelope_summary: dict[str, Any] = {}

        self._websocket_integrity_enabled = _source_is_websocket(self.adapter.delta_source)
        self._sync_engine: OrderBookSyncEngine | None = None
        self._gap_detector: GapDetectionModule | None = None
        self._resilience: ConnectionResilienceManager | None = None
        self._metrics: MarketPipelineMetrics | None = None
        if self._websocket_integrity_enabled:
            self._sync_engine = OrderBookSyncEngine(
                exchange=self.adapter.exchange, symbol=self.symbol
            )
            self._gap_detector = GapDetectionModule()
            self._resilience = ConnectionResilienceManager(
                config=BackoffConfig(stale_after_seconds=max(0.1, self.ws_stale_after_seconds))
            )
            self._metrics = MarketPipelineMetrics()

    async def run_once(self) -> dict[str, Any]:
        try:
            if not self._bootstrapped:
                snapshot = await self.adapter.bootstrap_snapshot(self.symbol, limit=self.depth)
                if self._sync_engine is not None:
                    self._sync_engine.load_snapshot(snapshot)
                    if self._resilience is not None:
                        self._resilience.mark_heartbeat(now_seconds=time.monotonic())
                self._bootstrapped = True

            if self._websocket_integrity_enabled:
                delta = await self._poll_websocket_delta_with_integrity()
            else:
                delta = await self.adapter.poll_delta(self.symbol, limit=self.depth)
                self._last_delta_source = self.adapter.delta_source
                self._last_fallback_reason = None
            self._record_processed_delta_metrics(delta)
            envelope = await self.pipeline.publish_order_book_delta(delta, mode=self.mode)
            self._last_envelope_summary = _market_envelope_summary(envelope)
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

    async def _poll_websocket_delta_with_integrity(self) -> OrderBookDelta:
        now_monotonic = time.monotonic()
        source = "websocket"
        if self._resilience is not None and self._resilience.is_stale(now_seconds=now_monotonic):
            if now_monotonic < self._next_ws_probe_monotonic:
                source = "rest"

        if source == "rest":
            return await self._fetch_rest_snapshot_delta(reason="stream_stale_cutover")

        try:
            delta = await self.adapter.poll_delta(
                self.symbol,
                limit=self.depth,
                source_override="websocket",
            )
        except Exception as exc:  # noqa: BLE001 - websocket errors are expected and trigger fallback.
            if self._resilience is not None:
                backoff = self._resilience.record_disconnect(now_seconds=time.monotonic())
                self._next_ws_probe_monotonic = time.monotonic() + max(
                    self.ws_probe_interval_seconds, backoff
                )
            if self._metrics is not None:
                self._metrics.record_reconnect(now_seconds=time.time())
            if self.notification_bridge is not None:
                await self.notification_bridge.publish_system_health_event(
                    trace_id=str(uuid.uuid4()),
                    mode=self.mode,
                    event_type="system.exchange.connectivity_issue",
                    severity="WARNING",
                    reason=exc.__class__.__name__,
                    details={"symbol": self.symbol, "error": str(exc), "fallback": "rest"},
                )
            return await self._fetch_rest_snapshot_delta(reason="websocket_error_fallback")
        self._last_delta_source = "websocket"
        self._last_fallback_reason = None

        return await self._apply_integrity_to_websocket_delta(delta)

    async def _apply_integrity_to_websocket_delta(self, delta: OrderBookDelta) -> OrderBookDelta:
        if self._sync_engine is None or self._gap_detector is None:
            return delta
        current_sequence = self._sync_engine.current_sequence
        gap = self._gap_detector.evaluate(
            current_sequence=current_sequence,
            incoming_start=delta.sequence_start,
            incoming_end=delta.sequence_end,
        )
        if gap.action == "ignore_stale":
            return await self._fetch_rest_snapshot_delta(reason="websocket_stale_delta")
        if gap.action == "resync":
            return await self._fetch_rest_snapshot_delta(reason="sequence_gap_resync")

        try:
            accepted = self._sync_engine.apply_delta(delta)
        except OrderBookSequenceGapError:
            return await self._fetch_rest_snapshot_delta(reason="sequence_gap_exception")
        if not accepted:
            return await self._fetch_rest_snapshot_delta(reason="delta_rejected_as_stale")

        if self._resilience is not None:
            self._resilience.record_reconnect_success(now_seconds=time.monotonic())
        return delta

    async def _fetch_rest_snapshot_delta(self, *, reason: str) -> OrderBookDelta:
        snapshot = await self.adapter.bootstrap_snapshot(self.symbol, limit=self.depth)
        if self._sync_engine is not None:
            self._sync_engine.load_snapshot(snapshot)
        if self._metrics is not None:
            self._metrics.record_resync_request(now_seconds=time.time())
        self._last_delta_source = "rest"
        self._last_fallback_reason = reason
        self._next_ws_probe_monotonic = time.monotonic() + self.ws_probe_interval_seconds
        return _snapshot_to_delta(snapshot)

    def _record_processed_delta_metrics(self, delta: OrderBookDelta) -> None:
        if self._metrics is None:
            return
        timestamp_ms = delta.timestamp_ms
        if timestamp_ms is None:
            lag_ms = 0.0
        else:
            now_ms = int(time.time() * 1000)
            lag_ms = float(max(0, now_ms - int(timestamp_ms)))
        self._metrics.record_delta_processed(
            lag_ms=lag_ms,
            now_seconds=time.time(),
        )

    def integrity_snapshot(self) -> dict[str, Any]:
        if self._metrics is None:
            return {"enabled": False}
        return {
            "enabled": True,
            "exchange": self.adapter.exchange,
            "symbol": self.symbol,
            "pipeline_metrics": self._metrics.snapshot(now_seconds=time.time()),
            "current_sequence": self._sync_engine.current_sequence
            if self._sync_engine is not None
            else None,
        }

    def activity_snapshot(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "exchange": self.adapter.exchange,
            "symbol": self.symbol,
            "mode": self.mode,
            "delta_source": self._last_delta_source,
            "fallback_reason": self._last_fallback_reason,
            "integrity": self.integrity_snapshot(),
            "kline_intervals": list(self.kline_intervals),
        }
        if self._last_envelope_summary:
            payload["latest"] = dict(self._last_envelope_summary)
        return payload

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

    def activity_snapshot(self) -> dict[str, Any]:
        return {
            "workers_total": len(self.workers),
            "workers": [
                worker.activity_snapshot()
                if hasattr(worker, "activity_snapshot")
                else {"exchange": worker.adapter.exchange}
                for worker in self.workers
            ],
        }


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


def _source_is_websocket(value: str) -> bool:
    return value.strip().lower() in {"websocket", "ws"}


def _snapshot_to_delta(snapshot: OrderBookSnapshot) -> OrderBookDelta:
    return OrderBookDelta(
        exchange=snapshot.exchange,
        symbol=snapshot.symbol,
        sequence_start=snapshot.sequence,
        sequence_end=snapshot.sequence,
        timestamp_ms=snapshot.timestamp_ms,
        bids=snapshot.bids,
        asks=snapshot.asks,
    )


def _market_envelope_summary(envelope: Mapping[str, Any]) -> dict[str, Any]:
    payload = envelope.get("payload")
    if not isinstance(payload, Mapping):
        return {}
    bids = payload.get("bids")
    asks = payload.get("asks")
    best_bid = 0.0
    best_ask = 0.0
    if isinstance(bids, list) and bids:
        level = bids[0]
        if isinstance(level, Mapping):
            best_bid = float(level.get("price", 0.0) or 0.0)
    if isinstance(asks, list) and asks:
        level = asks[0]
        if isinstance(level, Mapping):
            best_ask = float(level.get("price", 0.0) or 0.0)
    return {
        "trace_id": str(envelope.get("trace_id", "")),
        "decision_id": str(envelope.get("decision_id", "")),
        "exchange": str(payload.get("exchange", "")),
        "symbol": str(payload.get("symbol", "")),
        "timestamp_ms": payload.get("timestamp_ms"),
        "sequence_start": payload.get("sequence_start"),
        "sequence_end": payload.get("sequence_end"),
        "best_bid": best_bid,
        "best_ask": best_ask,
    }
