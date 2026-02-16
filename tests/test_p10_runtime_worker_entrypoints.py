from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import uuid

import pytest
from sqlalchemy import create_engine, text

from services.shared.runtime.broker import InMemoryTopicBroker
from services.shared.runtime.database import RuntimeDatabaseConfigError
from services.workers import main as runtime_main
from services.workers.main import (
    RuntimeWorkerBuildResult,
    RuntimeWorkerSettings,
    build_runtime_broker,
    build_runtime_worker,
)


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
        require_database=False,
    )


def _oms_order_envelope(
    *,
    event_type: str,
    order_id: str,
    quantity: float,
    price: float,
    action: str = "BUY",
) -> dict[str, object]:
    return {
        "trace_id": str(uuid.uuid4()),
        "decision_id": str(uuid.uuid4()),
        "mode": "MOCK",
        "idempotency_key": f"{event_type}:{order_id}",
        "event_type": event_type,
        "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "payload": {
            "order_id": order_id,
            "symbol": "BTC/USDT",
            "mode": "MOCK",
            "action": action,
            "quantity": quantity,
            "fill_price": price,
            "fee_paid": 0.05,
        },
        "service": "real_execution_go",
    }


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
async def test_orchestrator_worker_runner_persists_memory_when_runtime_engine_is_provided(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'runtime-orchestrator.db'}")
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    build = build_runtime_worker(
        settings=_settings(worker="orchestrator"),
        broker=broker,
        runtime_engine=engine,
    )
    await broker.publish(routing_key="market.canonical", message=_market_envelope())

    worked = await build.worker.run_once(timeout_seconds=0.0)

    assert worked is True
    with engine.connect() as connection:
        summary_count = connection.execute(text("SELECT COUNT(*) FROM runtime_decision_memory")).scalar_one()
        slot_count = connection.execute(text("SELECT COUNT(*) FROM runtime_decision_slots")).scalar_one()
    assert summary_count >= 1
    assert slot_count >= 1


@pytest.mark.asyncio
async def test_market_worker_runner_persists_orderbook_snapshot_when_runtime_engine_is_provided(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'runtime-market.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE orderbook_snapshots (
                    snapshot_time TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    bids TEXT NOT NULL,
                    asks TEXT NOT NULL,
                    best_bid REAL NOT NULL,
                    best_ask REAL NOT NULL,
                    spread_bps REAL NOT NULL,
                    PRIMARY KEY (snapshot_time, exchange, symbol)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE klines (
                    time TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    "interval" TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    quote_volume REAL NOT NULL,
                    trades INTEGER NOT NULL,
                    PRIMARY KEY (time, exchange, symbol, "interval")
                )
                """
            )
        )

    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    build = build_runtime_worker(
        settings=_settings(worker="market"),
        broker=broker,
        runtime_engine=engine,
    )

    worked = await build.worker.run_once(timeout_seconds=0.0)

    assert worked is True
    with engine.connect() as connection:
        snapshot_count = connection.execute(text("SELECT COUNT(*) FROM orderbook_snapshots")).scalar_one()
    assert snapshot_count >= 1


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


@pytest.mark.asyncio
async def test_news_worker_runner_uses_real_rss_mode_when_database_is_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rss_xml = """
    <rss version="2.0">
      <channel>
        <item>
          <title>Market update</title>
          <link>https://news.example.com/market-update</link>
          <pubDate>Mon, 16 Feb 2026 00:00:00 GMT</pubDate>
          <description>BTC momentum stabilizes.</description>
        </item>
      </channel>
    </rss>
    """
    monkeypatch.setenv("NEWS_SOURCE_MODE", "mock")
    monkeypatch.setenv("NEWS_RSS_FEEDS", "https://news.example.com/rss")
    monkeypatch.setattr(runtime_main, "_http_get_text", lambda url, timeout_seconds: rss_xml)

    settings = RuntimeWorkerSettings(
        worker="news",
        broker_backend="inmemory",
        topology_path="config/rabbitmq/topology.json",
        mode="MOCK",
        symbol="BTC/USDT",
        strategy_id="default-strategy",
        once=True,
        validate_only=False,
        max_idle_cycles=0,
        poll_timeout_seconds=0.0,
        idle_sleep_seconds=0.0,
        bootstrap_topology=False,
        portfolio_base_balance_usd=100000.0,
        require_database=True,
    )
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    build = build_runtime_worker(settings=settings, broker=broker)

    worked = await build.worker.run_once(timeout_seconds=0.0)

    assert worked is True
    assert build.worker.source_mode == "real"
    cycle = build.worker.framework.fetch_cycle(limit_per_source=1)
    assert cycle.sources_total == 1
    assert cycle.results[0].source.startswith("rss.")
    assert cycle.results[0].source != "mock.crypto"


@pytest.mark.asyncio
async def test_oms_worker_runner_persists_state_when_runtime_engine_is_provided(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'runtime-oms.db'}")
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    build = build_runtime_worker(
        settings=_settings(worker="oms"),
        broker=broker,
        runtime_engine=engine,
    )
    await broker.publish(
        routing_key="oms.order.partially_filled",
        message=_oms_order_envelope(
            event_type="oms.order.partially_filled",
            order_id="order-persist-1",
            quantity=0.1,
            price=42000.0,
        ),
    )
    await broker.publish(
        routing_key="oms.order.filled",
        message=_oms_order_envelope(
            event_type="oms.order.filled",
            order_id="order-persist-1",
            quantity=0.2,
            price=42010.0,
        ),
    )

    worked_first = await build.worker.run_once(timeout_seconds=0.0)
    worked_second = await build.worker.run_once(timeout_seconds=0.0)

    assert worked_first is True
    assert worked_second is True
    with engine.connect() as connection:
        order_status = connection.execute(
            text(
                """
                SELECT status
                FROM runtime_oms_orders
                WHERE order_id = :order_id
                """
            ),
            {"order_id": "order-persist-1"},
        ).scalar_one()
        lifecycle_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM runtime_oms_lifecycle_events
                WHERE order_id = :order_id
                """
            ),
            {"order_id": "order-persist-1"},
        ).scalar_one()
        position_count = connection.execute(text("SELECT COUNT(*) FROM runtime_oms_positions")).scalar_one()
        snapshot_count = connection.execute(
            text("SELECT COUNT(*) FROM runtime_oms_portfolio_snapshots")
        ).scalar_one()

    assert order_status == "FILLED"
    assert lifecycle_count == 2
    assert position_count == 1
    assert snapshot_count >= 1


@pytest.mark.asyncio
async def test_news_worker_runner_persists_items_tags_and_summary_when_runtime_engine_is_provided(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'runtime-news.db'}")
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    build = build_runtime_worker(
        settings=_settings(worker="news"),
        broker=broker,
        runtime_engine=engine,
    )

    worked = await build.worker.run_once(timeout_seconds=0.0)

    assert worked is True
    with engine.connect() as connection:
        item_count = connection.execute(text("SELECT COUNT(*) FROM news_items")).scalar_one()
        tag_count = connection.execute(text("SELECT COUNT(*) FROM news_tags")).scalar_one()
        summary_count = connection.execute(text("SELECT COUNT(*) FROM news_summaries")).scalar_one()
    assert item_count >= 1
    assert tag_count >= 1
    assert summary_count >= 1


def test_runtime_worker_main_fails_fast_when_database_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_runtime_db_error() -> None:
        raise RuntimeDatabaseConfigError("database unavailable")

    monkeypatch.setattr(runtime_main, "create_runtime_engine_from_env", _raise_runtime_db_error)

    exit_code = runtime_main.main(["--worker", "news", "--validate-only", "--broker-backend", "inmemory"])

    assert exit_code == 1


def test_runtime_worker_main_rejects_inmemory_broker_under_runtime_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNTIME_REQUIRE_DATABASE", "true")

    exit_code = runtime_main.main(["--worker", "market", "--validate-only", "--broker-backend", "inmemory"])

    assert exit_code == 1


def test_market_worker_defaults_to_rest_fetch_mode_and_five_minute_cadence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MARKET_DATA_FETCH_MODE", raising=False)
    monkeypatch.delenv("MARKET_DATA_REST_POLL_SECONDS", raising=False)
    monkeypatch.delenv("ORDERBOOK_SNAPSHOT_INTERVAL_SECONDS", raising=False)

    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    build = build_runtime_worker(settings=_settings(worker="market"), broker=broker)

    assert build.worker.worker.adapter.delta_source == "rest"
    assert build.worker.min_cycle_interval_seconds == 180.0


def test_market_worker_orderbook_interval_overrides_rest_poll_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARKET_DATA_FETCH_MODE", "rest")
    monkeypatch.setenv("MARKET_DATA_REST_POLL_SECONDS", "300")
    monkeypatch.setenv("ORDERBOOK_SNAPSHOT_INTERVAL_SECONDS", "45")

    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    build = build_runtime_worker(settings=_settings(worker="market"), broker=broker)

    assert build.worker.min_cycle_interval_seconds == 45.0


def test_market_worker_supports_multi_exchange_single_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARKET_EXCHANGES", "binance,bitget")
    monkeypatch.setenv("MARKET_SYMBOLS", "BTC/USDT")

    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    build = build_runtime_worker(settings=_settings(worker="market"), broker=broker)

    assert hasattr(build.worker.worker, "workers")
    assert len(build.worker.worker.workers) == 2


def test_market_worker_websocket_mode_disables_rest_poll_cadence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARKET_DATA_FETCH_MODE", "websocket")
    monkeypatch.setenv("MARKET_DATA_REST_POLL_SECONDS", "300")

    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    build = build_runtime_worker(settings=_settings(worker="market"), broker=broker)

    assert build.worker.worker.adapter.delta_source == "websocket"
    assert build.worker.min_cycle_interval_seconds == 0.0


@pytest.mark.asyncio
async def test_run_worker_loop_recovers_from_runtime_errors_in_long_running_mode() -> None:
    class _FailingWorker:
        def __init__(self) -> None:
            self.calls = 0

        async def run_once(self, *, timeout_seconds: float) -> bool:
            _ = timeout_seconds
            self.calls += 1
            raise RuntimeError("transient exchange failure")

    settings = RuntimeWorkerSettings(
        worker="market",
        broker_backend="inmemory",
        topology_path="config/rabbitmq/topology.json",
        mode="MOCK",
        symbol="BTC/USDT",
        strategy_id="default-strategy",
        once=False,
        validate_only=False,
        max_idle_cycles=1,
        poll_timeout_seconds=0.0,
        idle_sleep_seconds=0.0,
        bootstrap_topology=False,
        portfolio_base_balance_usd=100000.0,
        require_database=False,
    )
    worker = _FailingWorker()
    build = RuntimeWorkerBuildResult(
        worker=worker,
        broker=InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json"),
    )

    exit_code = await runtime_main.run_worker_loop(settings=settings, build=build)

    assert exit_code == 0
    assert worker.calls == 1


@pytest.mark.asyncio
async def test_run_worker_loop_returns_failure_for_once_mode_runtime_errors() -> None:
    class _FailingWorker:
        async def run_once(self, *, timeout_seconds: float) -> bool:
            _ = timeout_seconds
            raise RuntimeError("transient exchange failure")

    settings = RuntimeWorkerSettings(
        worker="market",
        broker_backend="inmemory",
        topology_path="config/rabbitmq/topology.json",
        mode="MOCK",
        symbol="BTC/USDT",
        strategy_id="default-strategy",
        once=True,
        validate_only=False,
        max_idle_cycles=0,
        poll_timeout_seconds=0.0,
        idle_sleep_seconds=0.0,
        bootstrap_topology=False,
        portfolio_base_balance_usd=100000.0,
        require_database=False,
    )
    build = RuntimeWorkerBuildResult(
        worker=_FailingWorker(),
        broker=InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json"),
    )

    exit_code = await runtime_main.run_worker_loop(settings=settings, build=build)

    assert exit_code == 1
