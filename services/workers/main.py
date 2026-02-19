from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib import request
from urllib.parse import urlparse
import asyncio
import hashlib
import os
import time
import uuid
import xml.etree.ElementTree as ET

from sqlalchemy.engine import Engine

from services.agent_orchestrator.contracts import StrategyConfig
from services.agent_orchestrator.llm_runtime import LLMDecisionRuntime
from services.agent_orchestrator.memory_layer import AgentMemoryLayer
from services.agent_orchestrator.metrics_tracing import AgentRuntimeMetrics
from services.agent_orchestrator.orchestrator import AgentOrchestrator
from services.agent_orchestrator.sqlalchemy_memory_store import (
    SQLAlchemyLongTermMemoryStore,
    SQLAlchemyShortTermMemoryStore,
)
from services.agent_orchestrator.sqlalchemy_trace_store import SQLAlchemyTraceStore, TraceAgentRun
from services.llm_gateway.contracts import GatewaySettings, ProviderSettings
from services.llm_gateway.gateway import LLMGateway
from services.llm_gateway.litellm_http_adapter import LiteLLMHTTPProviderClient
from services.llm_gateway.sqlalchemy_stores import SQLAlchemyLLMCallStore, SQLAlchemyLLMQuotaStore
from services.market_ingestion.canonical_pipeline import CanonicalNormalizationPipeline
from services.market_ingestion.binance_http_adapter import BinanceHTTPOrderBookClient
from services.market_ingestion.bitget_http_adapter import BitgetHTTPOrderBookClient
from services.market_ingestion.ccxt_pro_adapter import CCXTProOrderBookClient
from services.market_ingestion.exchange_adapter import CCXTIngestionAdapter
from services.news_ingestion.ingestion_service import InMemoryNewsItemStore, NewsIngestionService
from services.news_ingestion.x_provider_connector import XProviderConnector
from services.news_ingestion.source_connectors import (
    CallableSourceConnector,
    NewsSourceConnectorFramework,
    SourceConnectorRegistry,
)
from services.news_ingestion.tagging_relevance import InMemoryNewsTagStore, NewsTaggingRelevancePipeline
from services.news_summarizer.summarizer_service import InMemoryNewsSummaryStore, RollingNewsSummarizer
from services.oms.fill_reconciliation import FillReconciliationEngine, LifecycleEvent, ReconciliationOrder
from services.oms.portfolio_snapshot import PortfolioSnapshotEngine
from services.oms.position_engine import PositionEngine, PositionFill, PositionState
from services.shared.runtime.broker import InMemoryTopicBroker
from services.shared.runtime.database import RuntimeDatabaseConfigError, create_runtime_engine_from_env
from services.shared.runtime.env_loader import load_dotenv_file
from services.shared.runtime.rabbitmq_http_broker import RabbitMQHTTPTopicBroker
from services.shared.runtime.structured_logging import StructuredLogger
from services.simulation_execution.worker import SimulationExecutionWorker
from services.workers.execution_lifecycle import (
    CCXTProPrivateOrderStreamConnector,
    ExecutionLifecycleWorker,
    NoopPrivateOrderStreamConnector,
    SignedRESTOrderStatusPoller,
)
from services.workers.runtime_persistence import (
    SQLAlchemyRuntimeMarketStore,
    SQLAlchemyNewsItemStore,
    SQLAlchemyNewsSummaryStore,
    SQLAlchemyNewsTagStore,
    SQLAlchemyRuntimeOMSStateStore,
)
from services.workers.runtime_pipeline import AgentOrchestratorRuntimeWorker, MarketIngestionRuntimeWorker
from services.workers.runtime_pipeline import MultiExchangeMarketIngestionRuntimeWorker, MarketRuntimeWorker

_WORKER_SERVICE_NAME = "runtime_worker"
_WORKER_CHOICES = ("market", "orchestrator", "simulation", "oms", "news", "execution_lifecycle")
_NEWS_SOURCE_ITEM_ID_MAX_LEN = 128


class RuntimeWorkerRunner(Protocol):
    async def run_once(self, *, timeout_seconds: float) -> bool: ...


@dataclass(frozen=True, slots=True)
class RuntimeWorkerSettings:
    worker: str
    broker_backend: str
    topology_path: str
    mode: str
    symbol: str
    strategy_id: str
    once: bool
    validate_only: bool
    max_idle_cycles: int
    poll_timeout_seconds: float
    idle_sleep_seconds: float
    bootstrap_topology: bool
    portfolio_base_balance_usd: float
    require_database: bool = True


@dataclass(frozen=True, slots=True)
class RuntimeWorkerBuildResult:
    worker: RuntimeWorkerRunner
    broker: Any


class _SyntheticRestOrderBookClient:
    def __init__(self, *, base_price: float) -> None:
        self.base_price = max(base_price, 1.0)

    async def fetch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, Any]:
        _ = symbol, limit
        return _build_order_book_payload(
            base_price=self.base_price,
            sequence=1000,
            timestamp_ms=_utc_now_ms(),
        )

    async def fetch_klines(
        self,
        symbol: str,
        *,
        interval: str,
        limit: int = 200,
    ) -> tuple[dict[str, Any], ...]:
        _ = symbol, interval, limit
        now_ms = _utc_now_ms()
        return (
            {
                "open_time_ms": now_ms - 60_000,
                "open": self.base_price - 3.0,
                "high": self.base_price + 8.0,
                "low": self.base_price - 10.0,
                "close": self.base_price + 2.0,
                "volume": 25.0,
                "quote_volume": 25.0 * self.base_price,
                "trades": 80,
            },
        )


class _SyntheticWsOrderBookClient:
    def __init__(self, *, base_price: float) -> None:
        self.base_price = max(base_price, 1.0)
        self._sequence = 1000

    async def watch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, Any]:
        _ = symbol, limit
        self._sequence += 1
        price_shift = ((self._sequence % 6) - 3) * 0.5
        return _build_order_book_payload(
            base_price=self.base_price + price_shift,
            sequence=self._sequence,
            timestamp_ms=_utc_now_ms(),
        )


class MarketWorkerRunner:
    def __init__(
        self,
        *,
        worker: MarketRuntimeWorker,
        min_cycle_interval_seconds: float = 0.0,
    ) -> None:
        self.worker = worker
        self.min_cycle_interval_seconds = max(0.0, float(min_cycle_interval_seconds))
        self._last_run_monotonic: float | None = None

    async def run_once(self, *, timeout_seconds: float) -> bool:
        _ = timeout_seconds
        if self._last_run_monotonic is not None and self.min_cycle_interval_seconds > 0:
            elapsed = time.monotonic() - self._last_run_monotonic
            remaining = self.min_cycle_interval_seconds - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)
        cycle_started = time.monotonic()
        try:
            await self.worker.run_once()
        finally:
            # Keep cadence even on transient fetch failures to avoid tight retry loops.
            self._last_run_monotonic = cycle_started
        return True


class OrchestratorWorkerRunner:
    def __init__(
        self,
        *,
        worker: AgentOrchestratorRuntimeWorker,
        strategy: StrategyConfig,
        trace_store: SQLAlchemyTraceStore | None = None,
    ) -> None:
        self.worker = worker
        self.strategy = strategy
        self.trace_store = trace_store

    async def run_once(self, *, timeout_seconds: float) -> bool:
        result = await self.worker.run_once(
            strategy=self.strategy,
            timeout_seconds=timeout_seconds,
        )
        if result is None:
            return False
        if self.trace_store is not None:
            await self.trace_store.persist_cycle(
                trace_id=result.trace_id,
                decision_id=result.decision_id,
                strategy_id=self.strategy.strategy_id,
                mode=result.mode,
                status=result.status,
                started_at=_decision_started_at(result.lifecycle),
                completed_at=_decision_completed_at(result.lifecycle),
                runs=_build_trace_runs(
                    result=result,
                    strategy=self.strategy,
                    last_market_envelope=self.worker.last_envelope,
                    recent_spans=_decision_spans(self.worker, decision_id=result.decision_id),
                ),
                decision_news_links=_decision_news_links(self.worker.last_envelope),
            )
        return True


class SimulationWorkerRunner:
    def __init__(self, *, worker: SimulationExecutionWorker) -> None:
        self.worker = worker

    async def run_once(self, *, timeout_seconds: float) -> bool:
        result = await self.worker.run_once(timeout_seconds=timeout_seconds)
        return result is not None


class OMSLifecycleWorkerRunner:
    """Stateful OMS loop for reconciliation, position updates, and snapshots."""

    def __init__(
        self,
        *,
        broker: Any,
        base_balance_usd: float,
        state_store: SQLAlchemyRuntimeOMSStateStore | None = None,
    ) -> None:
        self.broker = broker
        self.base_balance_usd = base_balance_usd
        self.state_store = state_store
        self.reconciliation = FillReconciliationEngine()
        self.position_engine = PositionEngine()
        self.snapshot_engine = PortfolioSnapshotEngine()
        self._orders: dict[str, ReconciliationOrder] = {}
        self._lifecycle_events: dict[str, list[LifecycleEvent]] = {}
        self._positions: dict[str, PositionState] = {}
        self._mark_prices: dict[str, float] = {}

    async def run_once(self, *, timeout_seconds: float) -> bool:
        envelope = await self.broker.consume(
            queue_name="oms.events.order_updates",
            timeout_seconds=timeout_seconds,
        )
        if envelope is None:
            return False

        payload = envelope.get("payload")
        if not isinstance(payload, Mapping):
            return False
        order_id = str(payload.get("order_id", "")).strip()
        symbol = str(payload.get("symbol", "")).strip()
        mode = str(payload.get("mode", "MOCK")).strip().upper() or "MOCK"
        if not order_id or not symbol:
            return False

        requested_quantity = abs(float(payload.get("quantity", 0.0) or 0.0))
        if self.state_store is None:
            existing_order = self._orders.get(
                order_id,
                ReconciliationOrder(
                    order_id=order_id,
                    symbol=symbol,
                    mode=mode,
                    requested_quantity=requested_quantity,
                ),
            )
        else:
            existing_order = self.state_store.get_order(order_id=order_id) or ReconciliationOrder(
                order_id=order_id,
                symbol=symbol,
                mode=mode,
                requested_quantity=requested_quantity,
            )
        lifecycle_event = _to_lifecycle_event(envelope)
        if self.state_store is None:
            events_for_order = self._lifecycle_events.setdefault(order_id, [])
            events_for_order.append(lifecycle_event)
        else:
            self.state_store.append_lifecycle_event(order_id=order_id, event=lifecycle_event)
            events_for_order = list(self.state_store.load_lifecycle_events(order_id=order_id))

        reconciliation = self.reconciliation.reconcile(
            order=existing_order,
            lifecycle_events=tuple(events_for_order),
            exchange_snapshot=None,
        )
        updated_order = ReconciliationOrder(
            order_id=order_id,
            symbol=symbol,
            mode=mode,
            requested_quantity=existing_order.requested_quantity,
            status=reconciliation.status,
            filled_quantity=reconciliation.filled_quantity,
            average_price=reconciliation.average_price,
        )
        if self.state_store is None:
            self._orders[order_id] = updated_order
        else:
            self.state_store.upsert_order(updated_order)

        if lifecycle_event.fill is not None:
            fill = lifecycle_event.fill
            side = str(payload.get("action", "BUY")).upper()
            if self.state_store is None:
                current = self._positions.get(symbol)
            else:
                current = self.state_store.get_position(mode=mode, symbol=symbol)
            position_update = self.position_engine.apply_fill(
                position=current,
                fill=PositionFill(
                    order_id=order_id,
                    mode=mode,
                    symbol=symbol,
                    side=side,
                    quantity=fill.quantity,
                    price=fill.price,
                    fee=fill.fee,
                    filled_at=str(envelope.get("emitted_at", _utc_now_iso())),
                ),
            )
            if self.state_store is None:
                self._positions[symbol] = position_update.current
                self._mark_prices[symbol] = fill.price
            else:
                self.state_store.upsert_position(position_update.current)
                self.state_store.upsert_mark_price(mode=mode, symbol=symbol, mark_price=fill.price)

        if self.state_store is None:
            positions = tuple(self._positions.values())
            mark_prices = dict(self._mark_prices)
        else:
            positions = self.state_store.list_positions(mode=mode)
            mark_prices = self.state_store.load_mark_prices(mode=mode)

        snapshot = self.snapshot_engine.build_snapshot(
            mode=mode,
            available_balance_usd=self.base_balance_usd,
            locked_balance_usd=0.0,
            positions=positions,
            mark_prices=mark_prices,
            realized_pnl_today=sum(position.realized_pnl for position in positions),
        )
        if self.state_store is not None:
            self.state_store.insert_portfolio_snapshot(snapshot)
        return True


class NewsWorkerRunner:
    def __init__(
        self,
        *,
        item_store: Any | None = None,
        tag_store: Any | None = None,
        summary_store: Any | None = None,
        source_mode: str = "mock",
        rss_feeds: tuple[str, ...] = (),
        fetch_timeout_seconds: float = 8.0,
        x_enabled: bool = False,
        x_api_base_url: str = "https://api.x.com/2/tweets/search/recent",
        x_bearer_token: str | None = None,
        x_query: str = "bitcoin OR ethereum OR solana",
    ) -> None:
        self.item_store = item_store or InMemoryNewsItemStore()
        self.tag_store = tag_store or InMemoryNewsTagStore()
        self.summary_store = summary_store or InMemoryNewsSummaryStore()
        self.source_mode = source_mode.strip().lower() or "mock"
        self.rss_feeds = tuple(feed.strip() for feed in rss_feeds if feed.strip())
        self.fetch_timeout_seconds = max(1.0, float(fetch_timeout_seconds))
        self.x_enabled = bool(x_enabled)
        self.x_api_base_url = x_api_base_url.strip()
        self.x_bearer_token = (x_bearer_token or "").strip()
        self.x_query = x_query.strip() or "bitcoin OR ethereum OR solana"

        registry = SourceConnectorRegistry()
        if self.source_mode == "real":
            feeds = self.rss_feeds or _default_news_rss_feeds()
            for idx, feed_url in enumerate(feeds):
                connector_id = f"rss.{_infer_source_name(feed_url)}.{idx + 1}"
                registry.register(
                    CallableSourceConnector(
                        connector_id=connector_id,
                        connector_kind="rss",
                        fetcher=lambda since, limit, _feed_url=feed_url: self._fetch_rss_records(
                            feed_url=_feed_url,
                            since=since,
                            limit=limit,
                        ),
                    )
                )
            if self.x_enabled and self.x_bearer_token:
                x_connector = XProviderConnector(
                    connector_id="social.x",
                    api_base_url=self.x_api_base_url,
                    bearer_token=self.x_bearer_token,
                    query=self.x_query,
                    timeout_seconds=self.fetch_timeout_seconds,
                )
                registry.register(
                    CallableSourceConnector(
                        connector_id="social.x",
                        connector_kind="social",
                        fetcher=lambda since, limit: x_connector.fetch_records(since=since, limit=limit),
                    )
                )
        else:
            registry.register(
                CallableSourceConnector(
                    connector_id="mock.crypto",
                    connector_kind="custom",
                    fetcher=self._fetch_mock_records,
                )
            )
        self.framework = NewsSourceConnectorFramework(registry=registry)
        self.ingestion = NewsIngestionService(store=self.item_store)
        self.tagging = NewsTaggingRelevancePipeline(store=self.tag_store)
        self.summarizer = RollingNewsSummarizer(store=self.summary_store)

    async def run_once(self, *, timeout_seconds: float) -> bool:
        _ = timeout_seconds
        cycle = self.framework.fetch_cycle(limit_per_source=10)
        if cycle.total_items == 0:
            return False

        batch = self.ingestion.ingest(cycle.items)
        inserted = tuple(
            outcome.item
            for outcome in batch.outcomes
            if outcome.inserted and outcome.item is not None
        )
        if not inserted:
            return False

        tag_result = self.tagging.tag_items(inserted)
        self.summarizer.summarize_window(
            symbol_scope="GLOBAL",
            window_start=_utc_now_iso(),
            window_end=_utc_now_iso(),
            items=inserted,
            tags=tag_result.tags,
            max_items=5,
        )
        return True

    def _fetch_mock_records(self, *, since: str | None, limit: int) -> list[dict[str, Any]]:
        _ = since
        if limit <= 0:
            return []
        now_iso = _utc_now_iso()
        return [
            {
                "source": "mock.crypto",
                "source_item_id": f"mock-{int(time.time())}",
                "published_at": now_iso,
                "title": "Bitcoin volatility cools as ETF inflows stabilize",
                "url": "https://example.local/news/mock-bitcoin",
                "content": "Risk appetite improves and exchange flows normalize.",
                "metadata": {"language": "en"},
            }
        ]

    def _fetch_rss_records(self, *, feed_url: str, since: str | None, limit: int) -> list[dict[str, Any]]:
        _ = since
        if limit <= 0:
            return []
        rss_xml = _http_get_text(feed_url, timeout_seconds=self.fetch_timeout_seconds)
        return _parse_rss_items(feed_url=feed_url, rss_xml=rss_xml, limit=limit)


def load_runtime_worker_settings(args: Namespace | None = None) -> RuntimeWorkerSettings:
    load_dotenv_file()
    parsed = args or _parse_args(None)
    default_backend = os.getenv("RUNTIME_BROKER_BACKEND", "rabbitmq_http")
    default_mode = os.getenv("EXECUTION_MODE_DEFAULT", "MOCK")
    return RuntimeWorkerSettings(
        worker=parsed.worker,
        broker_backend=(parsed.broker_backend or default_backend).strip().lower(),
        topology_path=parsed.topology_path,
        mode=(parsed.mode or default_mode).strip().upper(),
        symbol=(parsed.symbol or os.getenv("TRADE_SYMBOL", "BTC/USDT")).strip().upper(),
        strategy_id=(parsed.strategy_id or os.getenv("STRATEGY_ID", "default-strategy")).strip(),
        once=bool(parsed.once),
        validate_only=bool(parsed.validate_only),
        max_idle_cycles=max(0, int(parsed.max_idle_cycles)),
        poll_timeout_seconds=max(0.0, float(parsed.poll_timeout_seconds)),
        idle_sleep_seconds=max(0.0, float(parsed.idle_sleep_seconds)),
        bootstrap_topology=bool(parsed.bootstrap_topology),
        portfolio_base_balance_usd=max(
            0.0,
            float(
                os.getenv(
                    "OMS_PORTFOLIO_BASE_BALANCE_USD",
                    "100000.0",
                )
            ),
        ),
        require_database=_to_bool(os.getenv("RUNTIME_REQUIRE_DATABASE", "true")),
    )


def build_runtime_worker(
    *,
    settings: RuntimeWorkerSettings,
    broker: Any | None = None,
    runtime_engine: Engine | None = None,
) -> RuntimeWorkerBuildResult:
    runtime_broker = broker or build_runtime_broker(
        backend=settings.broker_backend,
        topology_path=settings.topology_path,
    )
    if settings.worker == "market":
        market_worker = _build_market_worker(
            settings=settings,
            broker=runtime_broker,
            runtime_engine=runtime_engine,
        )
        return RuntimeWorkerBuildResult(
            worker=MarketWorkerRunner(
                worker=market_worker,
                min_cycle_interval_seconds=_market_worker_cycle_interval_seconds(),
            ),
            broker=runtime_broker,
        )
    if settings.worker == "orchestrator":
        memory_layer: AgentMemoryLayer | None = None
        trace_store: SQLAlchemyTraceStore | None = None
        metrics = AgentRuntimeMetrics()
        llm_runtime: LLMDecisionRuntime | None = None
        if runtime_engine is not None:
            memory_layer = AgentMemoryLayer(
                short_term_store=SQLAlchemyShortTermMemoryStore(connection=runtime_engine),
                long_term_store=SQLAlchemyLongTermMemoryStore(connection=runtime_engine),
                decision_ttl_seconds=max(60, int(os.getenv("AGENT_DECISION_TTL_SECONDS", "900"))),
            )
            trace_store = SQLAlchemyTraceStore(connection=runtime_engine)
            llm_runtime = _build_llm_runtime(
                runtime_engine=runtime_engine,
                metrics=metrics,
            )
        orchestrator_worker = AgentOrchestratorRuntimeWorker(
            broker_consumer=runtime_broker,
            orchestrator=AgentOrchestrator(
                publisher=runtime_broker,
                memory_layer=memory_layer,
                metrics=metrics,
                llm_runtime=llm_runtime,
            ),
        )
        strategy = _strategy_from_settings(settings=settings)
        return RuntimeWorkerBuildResult(
            worker=OrchestratorWorkerRunner(
                worker=orchestrator_worker,
                strategy=strategy,
                trace_store=trace_store,
            ),
            broker=runtime_broker,
        )
    if settings.worker == "simulation":
        simulation_worker = SimulationExecutionWorker(broker=runtime_broker)
        return RuntimeWorkerBuildResult(
            worker=SimulationWorkerRunner(worker=simulation_worker),
            broker=runtime_broker,
        )
    if settings.worker == "oms":
        state_store = (
            SQLAlchemyRuntimeOMSStateStore(connection=runtime_engine)
            if runtime_engine is not None
            else None
        )
        return RuntimeWorkerBuildResult(
            worker=OMSLifecycleWorkerRunner(
                broker=runtime_broker,
                base_balance_usd=settings.portfolio_base_balance_usd,
                state_store=state_store,
            ),
            broker=runtime_broker,
        )
    if settings.worker == "execution_lifecycle":
        execution_lifecycle_worker = _build_execution_lifecycle_worker(
            broker=runtime_broker,
            timeout_seconds=settings.poll_timeout_seconds,
        )
        return RuntimeWorkerBuildResult(worker=execution_lifecycle_worker, broker=runtime_broker)
    if settings.worker == "news":
        source_mode = _resolve_news_source_mode(require_database=settings.require_database)
        rss_feeds = _parse_csv_tokens(os.getenv("NEWS_RSS_FEEDS")) or _default_news_rss_feeds()
        fetch_timeout_seconds = max(1.0, float(os.getenv("NEWS_FETCH_TIMEOUT_SECONDS", "8.0")))
        x_enabled = _to_bool(os.getenv("NEWS_ENABLE_X_PROVIDER", "false"))
        x_api_base_url = os.getenv("NEWS_X_API_BASE_URL", "https://api.x.com/2/tweets/search/recent")
        x_bearer_token = os.getenv("NEWS_X_BEARER_TOKEN")
        x_query = os.getenv("NEWS_X_QUERY", "bitcoin OR ethereum OR solana")
        if runtime_engine is None:
            news_worker = NewsWorkerRunner(
                source_mode=source_mode,
                rss_feeds=rss_feeds,
                fetch_timeout_seconds=fetch_timeout_seconds,
                x_enabled=x_enabled,
                x_api_base_url=x_api_base_url,
                x_bearer_token=x_bearer_token,
                x_query=x_query,
            )
        else:
            news_worker = NewsWorkerRunner(
                item_store=SQLAlchemyNewsItemStore(connection=runtime_engine),
                tag_store=SQLAlchemyNewsTagStore(connection=runtime_engine),
                summary_store=SQLAlchemyNewsSummaryStore(connection=runtime_engine),
                source_mode=source_mode,
                rss_feeds=rss_feeds,
                fetch_timeout_seconds=fetch_timeout_seconds,
                x_enabled=x_enabled,
                x_api_base_url=x_api_base_url,
                x_bearer_token=x_bearer_token,
                x_query=x_query,
            )
        return RuntimeWorkerBuildResult(worker=news_worker, broker=runtime_broker)
    raise ValueError(f"unsupported runtime worker: {settings.worker}")


def build_runtime_broker(*, backend: str, topology_path: str) -> Any:
    normalized = backend.strip().lower()
    if normalized == "inmemory":
        return InMemoryTopicBroker.from_topology_file(topology_path)
    if normalized == "rabbitmq_http":
        return RabbitMQHTTPTopicBroker.from_env(topology_path=topology_path)
    raise ValueError("RUNTIME_BROKER_BACKEND must be 'inmemory' or 'rabbitmq_http'")


async def run_worker_loop(*, settings: RuntimeWorkerSettings, build: RuntimeWorkerBuildResult) -> int:
    logger = StructuredLogger(service=_WORKER_SERVICE_NAME)

    if settings.bootstrap_topology and hasattr(build.broker, "bootstrap_topology"):
        await build.broker.bootstrap_topology()

    if settings.validate_only:
        logger.info(
            event="runtime.worker.validation_passed",
            context={"worker": settings.worker, "broker_backend": settings.broker_backend},
        )
        return 0

    idle_cycles = 0
    while True:
        try:
            did_work = await build.worker.run_once(timeout_seconds=settings.poll_timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - runtime loops must survive transient dependency failures
            logger.error(
                event="runtime.worker.cycle_failed",
                context={
                    "worker": settings.worker,
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                },
            )
            if settings.once:
                return 1
            idle_cycles += 1
            if settings.max_idle_cycles > 0 and idle_cycles >= settings.max_idle_cycles:
                return 0
            await asyncio.sleep(settings.idle_sleep_seconds)
            continue

        if did_work:
            idle_cycles = 0
            if settings.once:
                return 0
            continue

        idle_cycles += 1
        if settings.once:
            return 0
        if settings.max_idle_cycles > 0 and idle_cycles >= settings.max_idle_cycles:
            return 0
        await asyncio.sleep(settings.idle_sleep_seconds)


def main(argv: list[str] | None = None) -> int:
    startup_logger = StructuredLogger(service=_WORKER_SERVICE_NAME)
    parsed_args = _parse_args(argv)
    try:
        settings = load_runtime_worker_settings(parsed_args)
        _validate_runtime_backend_policy(settings=settings)
        runtime_engine = _resolve_runtime_engine(settings=settings)
        build = build_runtime_worker(settings=settings, runtime_engine=runtime_engine)
        return asyncio.run(run_worker_loop(settings=settings, build=build))
    except (RuntimeDatabaseConfigError, ValueError) as exc:
        startup_logger.error(
            event="runtime.worker.startup.validation_failed",
            context={"error": str(exc)},
        )
        return 1


def _validate_runtime_backend_policy(*, settings: RuntimeWorkerSettings) -> None:
    if settings.require_database and settings.broker_backend == "inmemory":
        raise ValueError(
            "inmemory broker backend is disabled when RUNTIME_REQUIRE_DATABASE=true; use rabbitmq_http backend"
        )


def _resolve_runtime_engine(*, settings: RuntimeWorkerSettings) -> Engine | None:
    if not settings.require_database:
        return None
    runtime_engine = create_runtime_engine_from_env()
    with runtime_engine.connect() as connection:
        value = connection.exec_driver_sql("SELECT 1").scalar_one()
        if value != 1:
            raise RuntimeDatabaseConfigError("runtime database connectivity check returned an unexpected response")
    return runtime_engine


def _build_market_worker(
    *,
    settings: RuntimeWorkerSettings,
    broker: Any,
    runtime_engine: Engine | None,
) -> MarketRuntimeWorker:
    fetch_mode = _normalize_market_fetch_mode(os.getenv("MARKET_DATA_FETCH_MODE", "rest"))
    use_ccxt_pro = _to_bool(os.getenv("MARKET_USE_CCXT_PRO", "false"))
    ccxt_pro_timeout_ms = max(1000, int(os.getenv("MARKET_CCXT_PRO_TIMEOUT_MS", "10000")))
    base_price = float(os.getenv("RUNTIME_MARKET_BASE_PRICE", "42000"))
    http_timeout_seconds = max(0.1, float(os.getenv("MARKET_DATA_HTTP_TIMEOUT_SECONDS", "10.0")))
    kline_intervals = _parse_csv_tokens(os.getenv("KLINE_INTERVALS", "1m")) or ("1m",)
    kline_poll_interval_seconds = max(1.0, float(os.getenv("KLINE_POLL_INTERVAL_SECONDS", "60")))
    kline_fetch_limit = max(1, int(os.getenv("KLINE_FETCH_LIMIT", "200")))
    exchanges = _resolve_market_exchanges()
    symbols = _resolve_market_symbols(default_symbol=settings.symbol)

    state_store = SQLAlchemyRuntimeMarketStore(connection=runtime_engine) if runtime_engine is not None else None
    workers: list[MarketIngestionRuntimeWorker] = []
    for exchange in exchanges:
        if settings.require_database:
            if exchange == "binance":
                real_client = BinanceHTTPOrderBookClient(
                    base_url=os.getenv("BINANCE_BASE_URL", "https://api.binance.com"),
                    timeout_seconds=http_timeout_seconds,
                )
            elif exchange == "bitget":
                real_client = BitgetHTTPOrderBookClient(
                    base_url=os.getenv("BITGET_BASE_URL", "https://api.bitget.com"),
                    timeout_seconds=http_timeout_seconds,
                )
            else:
                raise ValueError("MARKET_EXCHANGES entries must be 'binance' or 'bitget'")
            if use_ccxt_pro:
                ccxt_client = CCXTProOrderBookClient(
                    exchange=exchange,
                    fallback_rest_client=real_client,
                    fallback_ws_client=real_client,
                    timeout_ms=ccxt_pro_timeout_ms,
                )
                rest_client = ccxt_client
                ws_client = ccxt_client
                kline_client = ccxt_client
            else:
                rest_client = real_client
                ws_client = real_client
                kline_client = real_client
        else:
            rest_client = _SyntheticRestOrderBookClient(base_price=base_price)
            ws_client = _SyntheticWsOrderBookClient(base_price=base_price)
            kline_client = rest_client

        for symbol in symbols:
            adapter = CCXTIngestionAdapter(
                exchange=exchange,
                rest_client=rest_client,
                ws_client=ws_client,
                delta_source=fetch_mode,
            )
            workers.append(
                MarketIngestionRuntimeWorker(
                    adapter=adapter,
                    pipeline=CanonicalNormalizationPipeline(publisher=broker),
                    symbol=symbol,
                    mode=settings.mode,
                    depth=20,
                    state_store=state_store,
                    kline_client=kline_client,
                    kline_intervals=kline_intervals,
                    kline_poll_interval_seconds=kline_poll_interval_seconds,
                    kline_fetch_limit=kline_fetch_limit,
                )
            )

    if len(workers) == 1:
        return workers[0]
    return MultiExchangeMarketIngestionRuntimeWorker(workers=tuple(workers))


def _build_execution_lifecycle_worker(*, broker: Any, timeout_seconds: float) -> ExecutionLifecycleWorker:
    private_stream_enabled = _to_bool(os.getenv("EXECUTION_PRIVATE_STREAM_ENABLED", "true"))
    private_stream_exchanges = _parse_csv_tokens(os.getenv("EXECUTION_PRIVATE_STREAM_EXCHANGES"))
    if not private_stream_exchanges:
        private_stream_exchanges = _resolve_market_exchanges()
    private_watch_timeout = max(
        0.1,
        float(os.getenv("EXECUTION_PRIVATE_STREAM_WATCH_TIMEOUT_SECONDS", str(max(0.1, timeout_seconds or 0.6)))),
    )
    if private_stream_enabled:
        private_stream_connector = CCXTProPrivateOrderStreamConnector(
            exchanges=tuple(exchange.lower() for exchange in private_stream_exchanges),
            watch_timeout_seconds=private_watch_timeout,
        )
    else:
        private_stream_connector = NoopPrivateOrderStreamConnector()

    lifecycle_queue_name = os.getenv("EXECUTION_LIFECYCLE_INTENT_QUEUE", "execution.intent.real.lifecycle").strip()
    if not lifecycle_queue_name:
        lifecycle_queue_name = "execution.intent.real.lifecycle"
    return ExecutionLifecycleWorker(
        broker=broker,
        private_stream_connector=private_stream_connector,
        status_poller=SignedRESTOrderStatusPoller(enable_real_dispatch=True),
        intent_queue_name=lifecycle_queue_name,
        stream_stale_after_seconds=max(
            0.0,
            float(os.getenv("EXECUTION_LIFECYCLE_STREAM_STALE_SECONDS", "15.0")),
        ),
        fallback_poll_interval_seconds=max(
            0.0,
            float(os.getenv("EXECUTION_LIFECYCLE_REST_POLL_INTERVAL_SECONDS", "5.0")),
        ),
        terminal_retention_seconds=max(
            0.0,
            float(os.getenv("EXECUTION_LIFECYCLE_TERMINAL_RETENTION_SECONDS", "600.0")),
        ),
        max_tracked_orders=max(
            10,
            int(os.getenv("EXECUTION_LIFECYCLE_MAX_TRACKED_ORDERS", "10000")),
        ),
    )


def _strategy_from_settings(*, settings: RuntimeWorkerSettings) -> StrategyConfig:
    return StrategyConfig(
        strategy_id=settings.strategy_id,
        symbol=settings.symbol,
        mode=settings.mode,
        order_size=float(os.getenv("STRATEGY_ORDER_SIZE", "0.1")),
        planner_buy_threshold=float(os.getenv("STRATEGY_PLANNER_BUY_THRESHOLD", "0.2")),
        planner_sell_threshold=float(os.getenv("STRATEGY_PLANNER_SELL_THRESHOLD", "0.2")),
        risk_max_notional_usd=float(os.getenv("STRATEGY_RISK_MAX_NOTIONAL_USD", "50000")),
        risk_max_position_size=float(os.getenv("STRATEGY_RISK_MAX_POSITION_SIZE", "1.0")),
        risk_max_drawdown_pct=float(os.getenv("STRATEGY_RISK_MAX_DRAWDOWN_PCT", "0.3")),
        risk_min_confidence=float(os.getenv("STRATEGY_RISK_MIN_CONFIDENCE", "0.2")),
    )


def _build_llm_runtime(
    *,
    runtime_engine: Engine,
    metrics: AgentRuntimeMetrics,
) -> LLMDecisionRuntime | None:
    if not _to_bool(os.getenv("LLM_RUNTIME_ENABLED", "false")):
        return None

    base_url = os.getenv("LITELLM_BASE_URL", "").strip()
    if not base_url:
        return None

    timeout_seconds = max(0.1, float(os.getenv("LITELLM_TIMEOUT_SECONDS", "15.0")))
    timeout_ms = max(1, int(timeout_seconds * 1000))
    retries = max(0, int(os.getenv("LLM_PROVIDER_MAX_RETRIES", "1")))

    openai_model = os.getenv("LLM_OPENAI_MODEL", "openai/gpt-4o-mini").strip() or "openai/gpt-4o-mini"
    anthropic_model = (
        os.getenv("LLM_ANTHROPIC_MODEL", "anthropic/claude-3-5-sonnet-20241022").strip()
        or "anthropic/claude-3-5-sonnet-20241022"
    )
    quick_order = tuple(_parse_csv_tokens(os.getenv("LLM_QUICK_PROVIDER_ORDER", "openai,anthropic")))
    deep_order = tuple(_parse_csv_tokens(os.getenv("LLM_DEEP_PROVIDER_ORDER", "anthropic,openai")))
    default_order = quick_order or ("openai", "anthropic")

    gateway_settings = GatewaySettings(
        providers={
            "openai": ProviderSettings(
                alias="openai",
                model=openai_model,
                timeout_ms=timeout_ms,
                max_retries=retries,
                enabled=True,
                prompt_cost_per_1k_tokens=float(os.getenv("LLM_OPENAI_PROMPT_COST_PER_1K", "0.0")),
                completion_cost_per_1k_tokens=float(os.getenv("LLM_OPENAI_COMPLETION_COST_PER_1K", "0.0")),
            ),
            "anthropic": ProviderSettings(
                alias="anthropic",
                model=anthropic_model,
                timeout_ms=timeout_ms,
                max_retries=retries,
                enabled=True,
                prompt_cost_per_1k_tokens=float(os.getenv("LLM_ANTHROPIC_PROMPT_COST_PER_1K", "0.0")),
                completion_cost_per_1k_tokens=float(os.getenv("LLM_ANTHROPIC_COMPLETION_COST_PER_1K", "0.0")),
            ),
        },
        default_provider_order=default_order,
        retry_base_ms=max(1, int(os.getenv("LLM_GATEWAY_RETRY_BASE_MS", "100"))),
        retry_max_ms=max(10, int(os.getenv("LLM_GATEWAY_RETRY_MAX_MS", "2000"))),
    )

    provider_client = LiteLLMHTTPProviderClient(
        base_url=base_url,
        api_key=os.getenv("LITELLM_API_KEY"),
        timeout_seconds=timeout_seconds,
    )
    gateway = LLMGateway(
        settings=gateway_settings,
        provider_clients={
            "openai": provider_client,
            "anthropic": provider_client,
        },
        call_store=SQLAlchemyLLMCallStore(connection=runtime_engine),
        quota_store=SQLAlchemyLLMQuotaStore(connection=runtime_engine),
        metrics=metrics,
    )
    return LLMDecisionRuntime(
        gateway=gateway,
        quick_provider_order=quick_order or ("openai", "anthropic"),
        deep_provider_order=deep_order or ("anthropic", "openai"),
        quick_temperature=float(os.getenv("LLM_QUICK_TEMPERATURE", "0.1")),
        deep_temperature=float(os.getenv("LLM_DEEP_TEMPERATURE", "0.2")),
    )


def _build_order_book_payload(*, base_price: float, sequence: int, timestamp_ms: int) -> dict[str, Any]:
    bid_0 = round(base_price - 0.5, 4)
    ask_0 = round(base_price + 0.5, 4)
    return {
        "nonce": sequence,
        "U": sequence,
        "u": sequence,
        "timestamp": timestamp_ms,
        "bids": [[bid_0, 5.0], [round(bid_0 - 1.0, 4), 2.5]],
        "asks": [[ask_0, 4.0], [round(ask_0 + 1.0, 4), 2.0]],
    }


def _to_lifecycle_event(envelope: Mapping[str, Any]) -> LifecycleEvent:
    event_type = str(envelope.get("event_type", ""))
    payload = envelope.get("payload")
    if not isinstance(payload, Mapping):
        return LifecycleEvent(event_type=event_type)
    if event_type not in {"oms.order.filled", "oms.order.partially_filled"}:
        return LifecycleEvent(event_type=event_type)
    order_id = str(payload.get("order_id", ""))
    if not order_id:
        return LifecycleEvent(event_type=event_type)
    fill_price = payload.get("fill_price", payload.get("price", 0.0))
    fill = PositionFill(
        order_id=order_id,
        mode=str(payload.get("mode", "MOCK")),
        symbol=str(payload.get("symbol", "")),
        side=str(payload.get("action", "BUY")),
        quantity=abs(float(payload.get("quantity", 0.0) or 0.0)),
        price=float(fill_price or 0.0),
        fee=float(payload.get("fee_paid", payload.get("fee", 0.0)) or 0.0),
        filled_at=str(envelope.get("emitted_at", _utc_now_iso())),
    )
    return LifecycleEvent(
        event_type=event_type,
        fill=_position_fill_to_reconciliation_fill(fill=fill),
    )


def _position_fill_to_reconciliation_fill(*, fill: PositionFill):
    from services.oms.fill_reconciliation import ReconciliationFill

    return ReconciliationFill(
        fill_id=f"fill:{fill.order_id}:{fill.filled_at or _utc_now_iso()}",
        order_id=fill.order_id,
        quantity=abs(float(fill.quantity)),
        price=float(fill.price),
        fee=float(fill.fee),
        source="runtime_worker",
    )


def _decision_spans(worker: AgentOrchestratorRuntimeWorker, *, decision_id: str) -> tuple[Mapping[str, Any], ...]:
    snapshot = worker.orchestrator.metrics.snapshot()
    spans = snapshot.get("recent_spans")
    if not isinstance(spans, list):
        return ()
    matched: list[Mapping[str, Any]] = []
    for span in spans:
        if not isinstance(span, Mapping):
            continue
        if str(span.get("decision_id", "")) != decision_id:
            continue
        matched.append(span)
    return tuple(matched)


def _build_trace_runs(
    *,
    result: Any,
    strategy: StrategyConfig,
    last_market_envelope: Mapping[str, Any] | None,
    recent_spans: tuple[Mapping[str, Any], ...],
) -> tuple[TraceAgentRun, ...]:
    span_by_stage = {str(item.get("stage", "")): item for item in recent_spans if isinstance(item, Mapping)}
    ordered_stages = (
        ("market_context_agent", "context", _context_stage_input(last_market_envelope), _context_stage_output(result)),
        ("planner_agent", "planner", _planner_stage_input(result), _planner_stage_output(result)),
        ("risk_agent", "risk", _risk_stage_input(result, strategy), _risk_stage_output(result)),
        (
            "execution_decision_agent",
            "execution",
            _execution_stage_input(result),
            _execution_stage_output(result),
        ),
        ("guardrail_validation", "guardrail", _guardrail_stage_input(result), _guardrail_stage_output(result)),
    )
    runs: list[TraceAgentRun] = []
    for stage_key, agent_name, input_payload, output_payload in ordered_stages:
        span = span_by_stage.get(stage_key)
        if span is None:
            status = "succeeded"
            latency_ms = None
            started_at = _decision_started_at(result.lifecycle)
            completed_at = _decision_completed_at(result.lifecycle)
        else:
            status = str(span.get("status", "succeeded"))
            latency_raw = span.get("latency_ms")
            latency_ms = float(latency_raw) if latency_raw is not None else None
            started_at = str(span.get("started_at", _utc_now_iso()))
            completed_at_raw = span.get("completed_at")
            completed_at = str(completed_at_raw) if completed_at_raw else None
        runs.append(
            TraceAgentRun(
                agent_name=agent_name,
                status=status,
                latency_ms=latency_ms,
                started_at=started_at,
                completed_at=completed_at,
                input_payload=input_payload,
                output_payload=output_payload,
            )
        )
    return tuple(runs)


def _context_stage_input(last_market_envelope: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(last_market_envelope, Mapping):
        return {}
    payload = last_market_envelope.get("payload")
    if not isinstance(payload, Mapping):
        return {}
    return {
        "exchange": payload.get("exchange"),
        "symbol": payload.get("symbol"),
        "timestamp_ms": payload.get("timestamp_ms"),
        "bids": _safe_list(payload.get("bids")),
        "asks": _safe_list(payload.get("asks")),
        "news": _safe_mapping(payload.get("news")),
    }


def _context_stage_output(result: Any) -> dict[str, Any]:
    output = {
        "context": _to_payload_mapping(getattr(result.market_context, "context", {})),
        "microstructure": _to_payload_mapping(getattr(result.market_context, "microstructure", {})),
        "news": _to_payload_mapping(getattr(result.market_context, "news", {})),
        "quality": _to_payload_mapping(getattr(result.market_context, "quality", {})),
        "notes": list(getattr(result.market_context, "notes", ()) or ()),
    }
    return output


def _planner_stage_input(result: Any) -> dict[str, Any]:
    return {"market_context": _to_payload_mapping(getattr(result.market_context, "context", {}))}


def _planner_stage_output(result: Any) -> dict[str, Any]:
    return _to_payload_mapping(getattr(result, "plan", {}))


def _risk_stage_input(result: Any, strategy: StrategyConfig) -> dict[str, Any]:
    return {
        "plan": _to_payload_mapping(getattr(result, "plan", {})),
        "market_context": _to_payload_mapping(getattr(result.market_context, "context", {})),
        "strategy": _to_payload_mapping(strategy),
    }


def _risk_stage_output(result: Any) -> dict[str, Any]:
    return _to_payload_mapping(getattr(result, "risk", {}))


def _execution_stage_input(result: Any) -> dict[str, Any]:
    return {
        "plan": _to_payload_mapping(getattr(result, "plan", {})),
        "risk": _to_payload_mapping(getattr(result, "risk", {})),
        "market_context": _to_payload_mapping(getattr(result.market_context, "context", {})),
    }


def _execution_stage_output(result: Any) -> dict[str, Any]:
    return _to_payload_mapping(getattr(result, "execution_decision", {}))


def _guardrail_stage_input(result: Any) -> dict[str, Any]:
    return {
        "plan": _to_payload_mapping(getattr(result, "plan", {})),
        "risk": _to_payload_mapping(getattr(result, "risk", {})),
        "execution_decision": _to_payload_mapping(getattr(result, "execution_decision", {})),
        "market_context": _to_payload_mapping(getattr(result.market_context, "context", {})),
    }


def _guardrail_stage_output(result: Any) -> dict[str, Any]:
    return _to_payload_mapping(getattr(result, "guardrail", {}))


def _decision_started_at(lifecycle: tuple[Mapping[str, Any], ...]) -> str:
    if lifecycle:
        first = lifecycle[0]
        emitted_at = first.get("emitted_at")
        if isinstance(emitted_at, str) and emitted_at.strip():
            return emitted_at
    return _utc_now_iso()


def _decision_completed_at(lifecycle: tuple[Mapping[str, Any], ...]) -> str:
    if lifecycle:
        last = lifecycle[-1]
        emitted_at = last.get("emitted_at")
        if isinstance(emitted_at, str) and emitted_at.strip():
            return emitted_at
    return _utc_now_iso()


def _decision_news_links(last_market_envelope: Mapping[str, Any] | None) -> tuple[tuple[str, str], ...]:
    if not isinstance(last_market_envelope, Mapping):
        return ()
    payload = last_market_envelope.get("payload")
    if not isinstance(payload, Mapping):
        return ()
    news = payload.get("news")
    if not isinstance(news, Mapping):
        return ()
    summary_id = _maybe_uuid(news.get("summary_id"))
    if summary_id is None:
        return ()
    news_ids: list[str] = []
    candidate_ids = news.get("news_ids")
    if isinstance(candidate_ids, list):
        for raw in candidate_ids:
            parsed = _maybe_uuid(raw)
            if parsed is not None:
                news_ids.append(parsed)
    items = news.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, Mapping):
                continue
            parsed = _maybe_uuid(item.get("news_id"))
            if parsed is not None:
                news_ids.append(parsed)
    deduped_news_ids = tuple(dict.fromkeys(news_ids))
    return tuple((summary_id, news_id) for news_id in deduped_news_ids)


def _to_payload_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    return {}


def _safe_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return dict(value)


def _safe_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return list(value)


def _maybe_uuid(value: Any) -> str | None:
    raw = str(value).strip() if value is not None else ""
    if not raw:
        return None
    try:
        return str(uuid.UUID(raw))
    except ValueError:
        return None


def _utc_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_args(argv: list[str] | None) -> Namespace:
    parser = ArgumentParser(description="Runtime worker entrypoints for phase-10 integration")
    parser.add_argument(
        "--worker",
        choices=_WORKER_CHOICES,
        required=True,
        help="worker role to run",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="process at most one work cycle and exit",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="build runtime dependencies and exit",
    )
    parser.add_argument(
        "--bootstrap-topology",
        action="store_true",
        help="bootstrap RabbitMQ topology before running the loop",
    )
    parser.add_argument(
        "--max-idle-cycles",
        type=int,
        default=0,
        help="exit after N empty polls (0 = unlimited)",
    )
    parser.add_argument(
        "--poll-timeout-seconds",
        type=float,
        default=float(os.getenv("RUNTIME_WORKER_POLL_TIMEOUT_SECONDS", "0.5")),
        help="queue poll timeout for consumer workers",
    )
    parser.add_argument(
        "--idle-sleep-seconds",
        type=float,
        default=float(os.getenv("RUNTIME_WORKER_IDLE_SLEEP_SECONDS", "0.5")),
        help="sleep duration between empty polls",
    )
    parser.add_argument(
        "--broker-backend",
        default=os.getenv("RUNTIME_BROKER_BACKEND"),
        help="runtime broker backend (inmemory or rabbitmq_http)",
    )
    parser.add_argument(
        "--topology-path",
        default="config/rabbitmq/topology.json",
        help="RabbitMQ topology path for inmemory and bootstrap flows",
    )
    parser.add_argument(
        "--mode",
        default=os.getenv("EXECUTION_MODE_DEFAULT"),
        help="runtime mode (MOCK or REAL)",
    )
    parser.add_argument(
        "--symbol",
        default=os.getenv("TRADE_SYMBOL", "BTC/USDT"),
        help="strategy/trading symbol",
    )
    parser.add_argument(
        "--strategy-id",
        default=os.getenv("STRATEGY_ID", "default-strategy"),
        help="strategy identifier",
    )
    return parser.parse_args(argv)


def _to_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")


def _normalize_market_fetch_mode(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"rest", "restful", "http"}:
        return "rest"
    if normalized in {"websocket", "ws"}:
        return "websocket"
    raise ValueError("MARKET_DATA_FETCH_MODE must be 'rest' or 'websocket'")


def _parse_csv_tokens(raw: str | None) -> tuple[str, ...]:
    if raw is None:
        return ()
    return tuple(token.strip() for token in raw.split(",") if token.strip())


def _resolve_market_exchanges() -> tuple[str, ...]:
    configured = _parse_csv_tokens(os.getenv("MARKET_EXCHANGES"))
    if not configured:
        fallback = os.getenv("EXCHANGE_DEFAULT", "binance").strip().lower()
        configured = (fallback,) if fallback else ("binance",)
    normalized = tuple(value.lower() for value in configured)
    invalid = tuple(value for value in normalized if value not in {"binance", "bitget"})
    if invalid:
        raise ValueError("MARKET_EXCHANGES entries must be binance or bitget")
    return normalized


def _resolve_market_symbols(*, default_symbol: str) -> tuple[str, ...]:
    configured = _parse_csv_tokens(os.getenv("MARKET_SYMBOLS"))
    if not configured:
        fallback = default_symbol.strip().upper()
        return (fallback,) if fallback else ("BTC/USDT",)
    return tuple(value.upper() for value in configured)


def _resolve_news_source_mode(*, require_database: bool) -> str:
    configured = os.getenv("NEWS_SOURCE_MODE", "").strip().lower()
    if configured and configured not in {"real", "mock"}:
        raise ValueError("NEWS_SOURCE_MODE must be 'real' or 'mock'")
    if require_database:
        return "real"
    return configured or "mock"


def _default_news_rss_feeds() -> tuple[str, ...]:
    return (
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
    )


def _orderbook_snapshot_interval_seconds() -> float:
    explicit = os.getenv("ORDERBOOK_SNAPSHOT_INTERVAL_SECONDS")
    if explicit is not None and explicit.strip():
        return max(0.0, float(explicit))
    if os.getenv("MARKET_DATA_REST_POLL_SECONDS", "").strip():
        return max(0.0, float(os.getenv("MARKET_DATA_REST_POLL_SECONDS", "300")))
    return 180.0


def _http_get_text(url: str, *, timeout_seconds: float) -> str:
    req = request.Request(url=url, method="GET")
    with request.urlopen(req, timeout=timeout_seconds) as response:  # noqa: S310 - explicit URL target
        return response.read().decode("utf-8", errors="ignore")


def _parse_rss_items(*, feed_url: str, rss_xml: str, limit: int) -> list[dict[str, Any]]:
    root = ET.fromstring(rss_xml)
    items: list[dict[str, Any]] = []
    source = _infer_source_name(feed_url)

    for item in root.findall(".//item"):
        title = _first_child_text(item, ("title",))
        link = _first_child_text(item, ("link",))
        published_at = _first_child_text(item, ("pubDate", "published")) or _utc_now_iso()
        description = _first_child_text(item, ("description", "summary"))
        if not title or not link:
            continue
        items.append(
            {
                "source": source,
                "source_item_id": _build_source_item_id(source=source, link=link),
                "title": title,
                "url": link,
                "published_at": published_at,
                "content": description,
                "metadata": {"language": "en"},
            }
        )
        if len(items) >= limit:
            return items

    for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        if len(items) >= limit:
            break
        title = _first_child_text(entry, ("{http://www.w3.org/2005/Atom}title",))
        updated = _first_child_text(entry, ("{http://www.w3.org/2005/Atom}updated",))
        content = _first_child_text(entry, ("{http://www.w3.org/2005/Atom}summary",))
        link = ""
        for link_node in entry.findall("{http://www.w3.org/2005/Atom}link"):
            href = str(link_node.attrib.get("href", "")).strip()
            if href:
                link = href
                break
        if not title or not link:
            continue
        items.append(
            {
                "source": source,
                "source_item_id": _build_source_item_id(source=source, link=link),
                "title": title,
                "url": link,
                "published_at": updated or _utc_now_iso(),
                "content": content,
                "metadata": {"language": "en"},
            }
        )
    return items


def _first_child_text(element: ET.Element, tags: tuple[str, ...]) -> str:
    for tag in tags:
        child = element.find(tag)
        if child is not None and child.text is not None and child.text.strip():
            return child.text.strip()
    return ""


def _infer_source_name(feed_url: str) -> str:
    parsed = urlparse(feed_url)
    hostname = (parsed.hostname or "unknown").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname or "unknown"


def _build_source_item_id(*, source: str, link: str) -> str:
    source_key = (source or "unknown").strip().lower()
    candidate = f"{source_key}:{link.strip()}"
    if len(candidate) <= _NEWS_SOURCE_ITEM_ID_MAX_LEN:
        return candidate
    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
    bounded_source = source_key[:63] if source_key else "unknown"
    return f"{bounded_source}:{digest}"


def _market_worker_cycle_interval_seconds() -> float:
    fetch_mode = _normalize_market_fetch_mode(os.getenv("MARKET_DATA_FETCH_MODE", "rest"))
    if fetch_mode == "rest":
        return _orderbook_snapshot_interval_seconds()
    return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
