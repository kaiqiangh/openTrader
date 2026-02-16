from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from services.agent_orchestrator.memory_layer import DecisionMemoryRecord
from services.agent_orchestrator.sqlalchemy_memory_store import (
    InMemoryTTLShortTermStore,
    SQLAlchemyShortTermMemoryStore,
    SQLAlchemyLongTermMemoryStore,
)
from services.llm_gateway.persistence import LLMCallRecord
from services.llm_gateway.sqlalchemy_stores import SQLAlchemyLLMCallStore, SQLAlchemyLLMQuotaStore
from services.market_ingestion.sqlalchemy_store import SQLAlchemyTimeseriesStore
from services.workers.runtime_persistence import SQLAlchemyRuntimeMarketStore


@pytest.mark.asyncio
async def test_timeseries_store_upserts_snapshot_and_kline(tmp_path) -> None:
    connection = sqlite3.connect(Path(tmp_path) / "timeseries.db")
    connection.execute(
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
    connection.execute(
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
    connection.commit()

    store = SQLAlchemyTimeseriesStore(connection=connection)
    await store.upsert_orderbook_snapshot(
        {
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "snapshot_time": "2026-02-14T15:00:00Z",
            "bids": [{"price": 42000.0, "amount": 2.0}],
            "asks": [{"price": 42001.0, "amount": 1.0}],
            "best_bid": 42000.0,
            "best_ask": 42001.0,
            "spread_bps": 0.24,
        }
    )
    await store.upsert_kline(
        {
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "interval_ms": 60_000,
            "open_time": "2026-02-14T15:00:00Z",
            "open": 42000.0,
            "high": 42010.0,
            "low": 41995.0,
            "close": 42005.0,
            "volume": 12.5,
        }
    )

    snapshot_count = connection.execute("SELECT COUNT(*) FROM orderbook_snapshots").fetchone()[0]
    kline_count = connection.execute("SELECT COUNT(*) FROM klines").fetchone()[0]
    assert snapshot_count == 1
    assert kline_count == 1


@pytest.mark.asyncio
async def test_memory_stores_persist_and_expire_slots(tmp_path) -> None:
    connection = sqlite3.connect(Path(tmp_path) / "memory.db")
    long_term = SQLAlchemyLongTermMemoryStore(connection=connection)

    now = [100.0]

    def _clock() -> float:
        return now[0]

    short_term = InMemoryTTLShortTermStore(clock=_clock)
    await short_term.write_slot(
        mode="MOCK",
        strategy_id="s-1",
        decision_id="d-1",
        slot="plan",
        payload={"action": "BUY"},
        ttl_seconds=10,
    )
    snapshot = await short_term.read_slots(mode="MOCK", strategy_id="s-1", decision_id="d-1")
    assert snapshot["plan"]["action"] == "BUY"

    now[0] = 111.0
    expired_snapshot = await short_term.read_slots(mode="MOCK", strategy_id="s-1", decision_id="d-1")
    assert expired_snapshot == {}

    record = DecisionMemoryRecord(
        trace_id="trace-1",
        decision_id="d-1",
        strategy_id="s-1",
        mode="MOCK",
        status="RISK_APPROVED",
        summary={"mid_price": 42000.0},
        lifecycle=({"event_type": "agent.decision.received"},),
        persisted_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    await long_term.persist_decision_summary(record)
    loaded = await long_term.read_decision_summary(decision_id="d-1")

    assert loaded is not None
    assert loaded.decision_id == "d-1"
    assert loaded.summary["mid_price"] == 42000.0


@pytest.mark.asyncio
async def test_sqlalchemy_short_term_memory_store_persists_slots(tmp_path) -> None:
    connection = sqlite3.connect(Path(tmp_path) / "memory-short-term.db")
    short_term = SQLAlchemyShortTermMemoryStore(connection=connection)

    await short_term.write_slot(
        mode="MOCK",
        strategy_id="strategy-1",
        decision_id="decision-1",
        slot="context",
        payload={"mid_price": 42000.0},
        ttl_seconds=600,
    )
    loaded = await short_term.read_slots(
        mode="MOCK",
        strategy_id="strategy-1",
        decision_id="decision-1",
    )

    assert loaded["context"]["mid_price"] == 42000.0


@pytest.mark.asyncio
async def test_llm_sqlalchemy_call_and_quota_stores(tmp_path) -> None:
    connection = sqlite3.connect(Path(tmp_path) / "llm.db")
    call_store = SQLAlchemyLLMCallStore(connection=connection, ensure_schema=True)
    quota_store = SQLAlchemyLLMQuotaStore(connection=connection, ensure_schema=True)

    connection.execute(
        """
        INSERT INTO llm_quota_limits
            (strategy_id, agent_name, daily_token_limit, monthly_cost_limit, is_hard_limit, created_at)
        VALUES
            ('strat-1', 'planner', 5000, 100.0, 1, '2026-02-14T00:00:00Z')
        """
    )
    connection.commit()

    await call_store.persist_call(
        LLMCallRecord(
            llm_call_id="call-1",
            trace_id="trace-1",
            decision_id="decision-1",
            strategy_id="strat-1",
            agent_name="planner",
            provider="litellm",
            model="gpt-4o-mini",
            prompt_payload={"messages": [{"role": "user", "content": "hello"}]},
            response_payload={"content": "ok"},
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            latency_ms=120.0,
            estimated_cost=0.01,
            created_at="2026-02-14T15:00:00Z",
        )
    )

    limits = await quota_store.get_limits(strategy_id="strat-1", agent_name="planner")
    assert limits.daily_token_limit == 5000
    assert limits.monthly_cost_limit == 100.0
    assert limits.is_hard_limit is True

    usage_before = await quota_store.get_usage(strategy_id="strat-1", agent_name="planner")
    assert usage_before.daily_tokens == 0

    usage_after = await quota_store.increment_usage(
        strategy_id="strat-1",
        agent_name="planner",
        added_tokens=200,
        added_cost=1.5,
    )
    assert usage_after.daily_tokens == 200
    assert usage_after.monthly_cost == pytest.approx(1.5)

    call_count = connection.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0]
    assert call_count == 1


@pytest.mark.asyncio
async def test_timeseries_store_accepts_sqlalchemy_engine(tmp_path) -> None:
    db_path = Path(tmp_path) / "timeseries-sa.db"
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
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

    store = SQLAlchemyTimeseriesStore(connection=engine)
    await store.upsert_orderbook_snapshot(
        {
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "snapshot_time": "2026-02-15T00:00:00Z",
            "bids": [{"price": 42000.0, "amount": 1.0}],
            "asks": [{"price": 42001.0, "amount": 1.0}],
            "best_bid": 42000.0,
            "best_ask": 42001.0,
            "spread_bps": 0.24,
        }
    )
    await store.upsert_kline(
        {
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "interval_ms": 60_000,
            "open_time": "2026-02-15T00:00:00Z",
            "open": 42000.0,
            "high": 42010.0,
            "low": 41990.0,
            "close": 42005.0,
            "volume": 10.0,
        }
    )
    with engine.connect() as connection:
        snapshot_count = connection.execute(text("SELECT COUNT(*) FROM orderbook_snapshots")).scalar_one()
        kline_count = connection.execute(text("SELECT COUNT(*) FROM klines")).scalar_one()
    assert snapshot_count == 1
    assert kline_count == 1


@pytest.mark.asyncio
async def test_runtime_market_store_persists_canonical_orderbook_envelope(tmp_path) -> None:
    db_path = Path(tmp_path) / "runtime-market-store.db"
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
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

    store = SQLAlchemyRuntimeMarketStore(connection=engine)
    await store.persist_orderbook_envelope(
        {
            "trace_id": "trace-market",
            "decision_id": "decision-market",
            "mode": "MOCK",
            "idempotency_key": "market.canonical:binance:1",
            "event_type": "market.canonical.orderbook_delta",
            "emitted_at": "2026-02-15T00:00:00Z",
            "payload": {
                "exchange": "binance",
                "symbol": "BTC/USDT",
                "timestamp_ms": 1739577600000,
                "bids": [{"price": 42000.0, "amount": 1.2}],
                "asks": [{"price": 42001.0, "amount": 0.8}],
            },
            "service": "market_ingestion",
        }
    )
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT exchange, symbol, best_bid, best_ask, spread_bps
                FROM orderbook_snapshots
                """
            )
        ).mappings().one()
    assert row["exchange"] == "binance"
    assert row["symbol"] == "BTC/USDT"
    assert row["best_bid"] == pytest.approx(42000.0)
    assert row["best_ask"] == pytest.approx(42001.0)
    assert row["spread_bps"] > 0.0


@pytest.mark.asyncio
async def test_runtime_market_store_persists_kline_rows(tmp_path) -> None:
    db_path = Path(tmp_path) / "runtime-market-store-klines.db"
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    with engine.begin() as connection:
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

    store = SQLAlchemyRuntimeMarketStore(connection=engine)
    await store.persist_kline_rows(
        exchange="binance",
        symbol="BTC/USDT",
        interval="1m",
        bars=(
            {
                "open_time_ms": 1739535600000,
                "open": 42000.0,
                "high": 42010.0,
                "low": 41990.0,
                "close": 42005.0,
                "volume": 12.5,
                "quote_volume": 525000.0,
                "trades": 120,
            },
            {
                "open_time_ms": 1739535660000,
                "open": 42005.0,
                "high": 42015.0,
                "low": 42000.0,
                "close": 42012.0,
                "volume": 11.0,
                "quote_volume": 462000.0,
                "trades": 110,
            },
        ),
    )

    with engine.connect() as connection:
        count = connection.execute(text("SELECT COUNT(*) FROM klines")).scalar_one()
    assert count == 2


@pytest.mark.asyncio
async def test_long_term_memory_store_accepts_sqlalchemy_engine(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{Path(tmp_path) / 'memory-sa.db'}")
    store = SQLAlchemyLongTermMemoryStore(connection=engine)

    record = DecisionMemoryRecord(
        trace_id="trace-sa",
        decision_id="decision-sa",
        strategy_id="strategy-sa",
        mode="MOCK",
        status="RISK_APPROVED",
        summary={"mid_price": 42000.0},
        lifecycle=({"event_type": "agent.decision.received"},),
        persisted_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    await store.persist_decision_summary(record)
    loaded = await store.read_decision_summary(decision_id="decision-sa")
    assert loaded is not None
    assert loaded.strategy_id == "strategy-sa"


@pytest.mark.asyncio
async def test_llm_store_accepts_sqlalchemy_engine(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{Path(tmp_path) / 'llm-sa.db'}")
    call_store = SQLAlchemyLLMCallStore(connection=engine, ensure_schema=True)
    quota_store = SQLAlchemyLLMQuotaStore(connection=engine, ensure_schema=True)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO llm_quota_limits
                    (strategy_id, agent_name, daily_token_limit, monthly_cost_limit, is_hard_limit, created_at)
                VALUES
                    (:strategy_id, :agent_name, :daily_token_limit, :monthly_cost_limit, :is_hard_limit, :created_at)
                """
            ),
            {
                "strategy_id": "strat-sa",
                "agent_name": "planner",
                "daily_token_limit": 1000,
                "monthly_cost_limit": 25.0,
                "is_hard_limit": 1,
                "created_at": "2026-02-15T00:00:00Z",
            },
        )

    await call_store.persist_call(
        LLMCallRecord(
            llm_call_id="call-sa",
            trace_id="trace-sa",
            decision_id="decision-sa",
            strategy_id="strat-sa",
            agent_name="planner",
            provider="litellm",
            model="gpt-4o-mini",
            prompt_payload={"messages": [{"role": "user", "content": "hello"}]},
            response_payload={"content": "ok"},
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            latency_ms=100.0,
            estimated_cost=0.02,
            created_at="2026-02-15T00:00:00Z",
        )
    )
    usage = await quota_store.increment_usage(
        strategy_id="strat-sa",
        agent_name="planner",
        added_tokens=100,
        added_cost=0.5,
    )
    limits = await quota_store.get_limits(strategy_id="strat-sa", agent_name="planner")

    assert limits.daily_token_limit == 1000
    assert usage.daily_tokens == 100

    with engine.connect() as connection:
        call_count = connection.execute(text("SELECT COUNT(*) FROM llm_calls")).scalar_one()
    assert call_count == 1
