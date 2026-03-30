"""Worker construction and broker building functions."""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy.engine import Engine

from services.agent_orchestrator.memory_layer import AgentMemoryLayer
from services.agent_orchestrator.metrics_tracing import AgentRuntimeMetrics
from services.agent_orchestrator.orchestrator import AgentOrchestrator
from services.agent_orchestrator.sqlalchemy_memory_store import (
    SQLAlchemyLongTermMemoryStore,
    SQLAlchemyShortTermMemoryStore,
)
from services.agent_orchestrator.sqlalchemy_trace_store import SQLAlchemyTraceStore
from services.market_ingestion.canonical_pipeline import CanonicalNormalizationPipeline
from services.market_ingestion.binance_http_adapter import BinanceHTTPOrderBookClient
from services.market_ingestion.bitget_http_adapter import BitgetHTTPOrderBookClient
from services.market_ingestion.ccxt_pro_adapter import CCXTProOrderBookClient
from services.market_ingestion.exchange_adapter import CCXTIngestionAdapter
from services.shared.runtime.broker import InMemoryTopicBroker
from services.shared.runtime.rabbitmq_http_broker import RabbitMQHTTPTopicBroker
from services.simulation_execution.worker import SimulationExecutionWorker
from services.workers.execution_lifecycle import (
    CCXTProPrivateOrderStreamConnector,
    ExecutionLifecycleWorker,
    NoopPrivateOrderStreamConnector,
    SignedRESTOrderStatusPoller,
)
from services.workers.helpers import (
    _default_news_rss_feeds,
    _normalize_market_fetch_mode,
    _parse_csv_tokens,
    _resolve_market_exchanges,
    _resolve_market_symbols,
    _resolve_news_source_mode,
    _to_bool,
)
from services.workers.market import (
    MarketWorkerRunner,
    _SyntheticRestOrderBookClient,
    _SyntheticWsOrderBookClient,
)
from services.workers.news import NewsWorkerRunner
from services.workers.oms_lifecycle import OMSLifecycleWorkerRunner
from services.workers.orchestrator import (
    OrchestratorWorkerRunner,
    _build_llm_runtime,
    _strategy_from_settings,
)
from services.workers.runtime_persistence import (
    SQLAlchemyRuntimeMarketStore,
    SQLAlchemyNewsItemStore,
    SQLAlchemyNewsSummaryStore,
    SQLAlchemyNewsTagStore,
    SQLAlchemyRuntimeOMSStateStore,
)
from services.workers.runtime_pipeline import (
    AgentOrchestratorRuntimeWorker,
    MarketIngestionRuntimeWorker,
    MultiExchangeMarketIngestionRuntimeWorker,
    MarketRuntimeWorker,
)
from services.workers.settings import RuntimeWorkerBuildResult, RuntimeWorkerSettings
from services.workers.simulation import SimulationWorkerRunner


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
        llm_runtime = None
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
        x_api_base_url = os.getenv(
            "NEWS_X_API_BASE_URL", "https://api.x.com/2/tweets/search/recent"
        )
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
    ws_stale_after_seconds = max(0.0, float(os.getenv("MARKET_WS_STALE_AFTER_SECONDS", "15.0")))
    ws_probe_interval_seconds = max(
        0.1, float(os.getenv("MARKET_WS_PROBE_INTERVAL_SECONDS", "5.0"))
    )
    exchanges = _resolve_market_exchanges()
    symbols = _resolve_market_symbols(default_symbol=settings.symbol)

    state_store = (
        SQLAlchemyRuntimeMarketStore(connection=runtime_engine)
        if runtime_engine is not None
        else None
    )
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
                    ws_stale_after_seconds=ws_stale_after_seconds,
                    ws_probe_interval_seconds=ws_probe_interval_seconds,
                )
            )

    if len(workers) == 1:
        return workers[0]
    return MultiExchangeMarketIngestionRuntimeWorker(workers=tuple(workers))


def _build_execution_lifecycle_worker(
    *, broker: Any, timeout_seconds: float
) -> ExecutionLifecycleWorker:
    private_stream_enabled = _to_bool(os.getenv("EXECUTION_PRIVATE_STREAM_ENABLED", "true"))
    private_stream_exchanges = _parse_csv_tokens(os.getenv("EXECUTION_PRIVATE_STREAM_EXCHANGES"))
    if not private_stream_exchanges:
        private_stream_exchanges = _resolve_market_exchanges()
    private_watch_timeout = max(
        0.1,
        float(
            os.getenv(
                "EXECUTION_PRIVATE_STREAM_WATCH_TIMEOUT_SECONDS",
                str(max(0.1, timeout_seconds or 0.6)),
            )
        ),
    )
    if private_stream_enabled:
        private_stream_connector = CCXTProPrivateOrderStreamConnector(
            exchanges=tuple(exchange.lower() for exchange in private_stream_exchanges),
            watch_timeout_seconds=private_watch_timeout,
        )
    else:
        private_stream_connector = NoopPrivateOrderStreamConnector()

    lifecycle_queue_name = os.getenv(
        "EXECUTION_LIFECYCLE_INTENT_QUEUE", "execution.intent.real.lifecycle"
    ).strip()
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


def _orderbook_snapshot_interval_seconds() -> float:
    explicit = os.getenv("ORDERBOOK_SNAPSHOT_INTERVAL_SECONDS")
    if explicit is not None and explicit.strip():
        return max(0.0, float(explicit))
    if os.getenv("MARKET_DATA_REST_POLL_SECONDS", "").strip():
        return max(0.0, float(os.getenv("MARKET_DATA_REST_POLL_SECONDS", "300")))
    return 180.0


def _worker_idle_heartbeat_cycles() -> int:
    raw = os.getenv("RUNTIME_WORKER_IDLE_HEARTBEAT_CYCLES", "20").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 20


def _market_worker_cycle_interval_seconds() -> float:
    fetch_mode = _normalize_market_fetch_mode(os.getenv("MARKET_DATA_FETCH_MODE", "rest"))
    if fetch_mode == "rest":
        return _orderbook_snapshot_interval_seconds()
    return 0.0
