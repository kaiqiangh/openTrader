from __future__ import annotations

import json

from fastapi.testclient import TestClient
import pytest

try:
    from sqlalchemy import create_engine, text
except ModuleNotFoundError:
    pytest.skip("sqlalchemy is not installed", allow_module_level=True)

from services.api.app import create_app
from services.api.repositories import ControlPlaneRepository
from services.api.settings import APISettings
from tests.jwt_test_helpers import encode_jwt_rs256, make_test_settings


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _settings() -> APISettings:
    return make_test_settings(read_only_mode=False)


def _repository(tmp_path) -> ControlPlaneRepository:
    db_path = tmp_path / "runtime_truth.db"
    engine = create_engine(f"sqlite+pysqlite:///{db_path}", future=True)
    return ControlPlaneRepository(engine=engine)


def test_control_mode_and_strategy_changes_are_restart_safe(tmp_path) -> None:
    settings = _settings()
    repo = _repository(tmp_path)
    operator = encode_jwt_rs256(subject="operator-user", role="operator", settings=settings)
    viewer = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)

    app1 = create_app(settings=settings, repository=repo)
    client1 = TestClient(app1)

    mode_change = client1.put(
        "/control/mode",
        headers=_auth_headers(operator),
        json={"mode": "REAL", "reason": "pilot"},
    )
    assert mode_change.status_code == 200
    assert mode_change.json()["mode"] == "REAL"

    strategy_change = client1.put(
        "/control/strategies/btc-momentum/state",
        headers=_auth_headers(operator),
        json={"state": "DISABLED", "reason": "maintenance"},
    )
    assert strategy_change.status_code == 200

    app2 = create_app(settings=settings, repository=repo)
    client2 = TestClient(app2)

    mode = client2.get("/control/mode", headers=_auth_headers(viewer))
    assert mode.status_code == 200
    assert mode.json()["mode"] == "REAL"

    strategies = client2.get("/control/strategies", headers=_auth_headers(viewer))
    assert strategies.status_code == 200
    btc = next(item for item in strategies.json()["items"] if item["strategy_id"] == "btc-momentum")
    assert btc["state"] == "DISABLED"
    assert btc["mode"] == "REAL"


def test_notification_preferences_are_restart_safe(tmp_path) -> None:
    settings = _settings()
    repo = _repository(tmp_path)
    admin = encode_jwt_rs256(subject="admin-user", role="admin", settings=settings)
    viewer = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)

    app1 = create_app(settings=settings, repository=repo)
    client1 = TestClient(app1)

    put_response = client1.put(
        "/ops/notifications/preferences/ops-primary",
        headers=_auth_headers(admin),
        json={
            "min_severity": "WARNING",
            "gateways": ["telegram"],
            "strategy_ids": ["btc-momentum"],
            "event_types": ["agent.decision.guardrail_rejected"],
        },
    )
    assert put_response.status_code == 200

    app2 = create_app(settings=settings, repository=repo)
    client2 = TestClient(app2)

    listing = client2.get(
        "/ops/notifications/preferences",
        headers=_auth_headers(viewer),
        params={"user_id": "ops-primary"},
    )
    assert listing.status_code == 200
    assert len(listing.json()["items"]) == 1
    assert listing.json()["items"][0]["user_id"] == "ops-primary"


def test_ops_market_and_history_endpoints_read_repository_data(tmp_path) -> None:
    settings = _settings()
    repo = _repository(tmp_path)
    viewer = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)

    with repo.engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS klines (
                    time TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    quote_volume REAL NOT NULL,
                    trades INTEGER NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS orderbook_snapshots (
                    snapshot_time TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    bids TEXT NOT NULL,
                    asks TEXT NOT NULL,
                    best_bid REAL NOT NULL,
                    best_ask REAL NOT NULL,
                    spread_bps REAL NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    snapshot_time TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    total_balance_usd REAL NOT NULL,
                    available_balance_usd REAL NOT NULL,
                    locked_balance_usd REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL,
                    realized_pnl_total REAL NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS runtime_decision_memory (
                    decision_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    lifecycle_json TEXT NOT NULL,
                    persisted_at TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS exchanges (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS symbols (
                    id TEXT PRIMARY KEY,
                    exchange_id TEXT NOT NULL,
                    symbol TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    exchange_id TEXT NOT NULL,
                    symbol_id TEXT NOT NULL,
                    side TEXT NOT NULL,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    filled_quantity REAL NOT NULL,
                    average_price REAL NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS fills (
                    id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    exchange_fill_id TEXT NOT NULL,
                    side TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    fee REAL NOT NULL,
                    fee_currency TEXT NULL,
                    filled_at TEXT NOT NULL
                )
                """
            )
        )

        connection.execute(
            text(
                """
                INSERT INTO klines(time, exchange, symbol, interval, open, high, low, close, volume, quote_volume, trades)
                VALUES(:time, :exchange, :symbol, :interval, :open, :high, :low, :close, :volume, :quote_volume, :trades)
                """
            ),
            {
                "time": "2026-02-19T19:00:00Z",
                "exchange": "binance",
                "symbol": "BTC/USDT",
                "interval": "1m",
                "open": 50000.0,
                "high": 50100.0,
                "low": 49900.0,
                "close": 50050.0,
                "volume": 10.0,
                "quote_volume": 500500.0,
                "trades": 42,
            },
        )

        connection.execute(
            text(
                """
                INSERT INTO orderbook_snapshots(snapshot_time, exchange, symbol, bids, asks, best_bid, best_ask, spread_bps)
                VALUES(:snapshot_time, :exchange, :symbol, :bids, :asks, :best_bid, :best_ask, :spread_bps)
                """
            ),
            {
                "snapshot_time": "2026-02-19T19:00:01Z",
                "exchange": "binance",
                "symbol": "BTC/USDT",
                "bids": '[{"price":50049.0,"amount":1.5}]',
                "asks": '[{"price":50051.0,"amount":1.2}]',
                "best_bid": 50049.0,
                "best_ask": 50051.0,
                "spread_bps": 0.399,
            },
        )

        connection.execute(
            text(
                """
                INSERT INTO portfolio_snapshots(snapshot_time, mode, total_balance_usd, available_balance_usd, locked_balance_usd, unrealized_pnl, realized_pnl_total)
                VALUES(:snapshot_time, :mode, :total, :available, :locked, :unrealized, :realized)
                """
            ),
            {
                "snapshot_time": "2026-02-19T19:00:05Z",
                "mode": "MOCK",
                "total": 100000.0,
                "available": 98000.0,
                "locked": 2000.0,
                "unrealized": 120.0,
                "realized": 45.0,
            },
        )

        connection.execute(
            text(
                """
                INSERT INTO runtime_decision_memory(decision_id, trace_id, strategy_id, mode, status, summary_json, lifecycle_json, persisted_at)
                VALUES(:decision_id, :trace_id, :strategy_id, :mode, :status, :summary_json, :lifecycle_json, :persisted_at)
                """
            ),
            {
                "decision_id": "b9270e5c-69fb-48c7-aa41-499f0e6b8ad7",
                "trace_id": "0dcbf5ff-35cb-4614-a7a9-c80f63ca40be",
                "strategy_id": "btc-momentum",
                "mode": "MOCK",
                "status": "RISK_APPROVED",
                "summary_json": json.dumps(
                    {
                        "execution_decision": {
                            "action": "BUY",
                            "quantity": 0.1,
                            "confidence": 0.73,
                        }
                    }
                ),
                "lifecycle_json": "[]",
                "persisted_at": "2026-02-19T19:00:07Z",
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO exchanges(id, name) VALUES(:id, :name)
                """
            ),
            {"id": "f7bedf4e-c1f4-4eb2-a6a7-6a9519de2dbe", "name": "binance"},
        )
        connection.execute(
            text(
                """
                INSERT INTO symbols(id, exchange_id, symbol) VALUES(:id, :exchange_id, :symbol)
                """
            ),
            {
                "id": "f1112dbf-0876-4336-b9b6-ecdcfbbd8d01",
                "exchange_id": "f7bedf4e-c1f4-4eb2-a6a7-6a9519de2dbe",
                "symbol": "BTC/USDT",
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO orders(id, exchange_id, symbol_id, side, type, status, mode, quantity, filled_quantity, average_price, updated_at)
                VALUES(:id, :exchange_id, :symbol_id, :side, :type, :status, :mode, :quantity, :filled_quantity, :average_price, :updated_at)
                """
            ),
            {
                "id": "23b0e84a-8448-4455-a89b-9a41f4c8605c",
                "exchange_id": "f7bedf4e-c1f4-4eb2-a6a7-6a9519de2dbe",
                "symbol_id": "f1112dbf-0876-4336-b9b6-ecdcfbbd8d01",
                "side": "BUY",
                "type": "MARKET",
                "status": "FILLED",
                "mode": "MOCK",
                "quantity": 0.1,
                "filled_quantity": 0.1,
                "average_price": 50050.0,
                "updated_at": "2026-02-19T19:00:08Z",
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO fills(id, order_id, exchange_fill_id, side, mode, quantity, price, fee, fee_currency, filled_at)
                VALUES(:id, :order_id, :exchange_fill_id, :side, :mode, :quantity, :price, :fee, :fee_currency, :filled_at)
                """
            ),
            {
                "id": "1020f6f3-677f-408d-9c2c-4b04b888fd49",
                "order_id": "23b0e84a-8448-4455-a89b-9a41f4c8605c",
                "exchange_fill_id": "fill-1",
                "side": "BUY",
                "mode": "MOCK",
                "quantity": 0.1,
                "price": 50050.0,
                "fee": 0.25,
                "fee_currency": "USDT",
                "filled_at": "2026-02-19T19:00:08Z",
            },
        )

    app = create_app(settings=settings, repository=repo)
    client = TestClient(app)

    klines = client.get(
        "/ops/market/klines",
        headers=_auth_headers(viewer),
        params={"symbol": "BTC/USDT", "interval": "1m"},
    )
    assert klines.status_code == 200
    assert len(klines.json()["items"]) == 1
    assert klines.json()["items"][0]["close"] == 50050.0

    orderbook = client.get(
        "/ops/market/orderbook/latest",
        headers=_auth_headers(viewer),
        params={"symbol": "BTC/USDT"},
    )
    assert orderbook.status_code == 200
    assert orderbook.json()["symbol"] == "BTC/USDT"
    assert orderbook.json()["best_ask"] == 50051.0

    history = client.get(
        "/ops/portfolio/history",
        headers=_auth_headers(viewer),
        params={"mode": "MOCK", "limit": 10},
    )
    assert history.status_code == 200
    assert len(history.json()["items"]) == 1
    assert history.json()["items"][0]["total_balance_usd"] == 100000.0

    signals = client.get(
        "/ops/signals/latest",
        headers=_auth_headers(viewer),
        params={"limit": 10},
    )
    assert signals.status_code == 200
    assert len(signals.json()["items"]) == 1
    assert signals.json()["items"][0]["action"] == "BUY"

    trades = client.get(
        "/ops/trades/latest",
        headers=_auth_headers(viewer),
        params={"mode": "MOCK", "symbol": "BTC/USDT", "limit": 10},
    )
    assert trades.status_code == 200
    assert len(trades.json()["items"]) == 1
    assert trades.json()["items"][0]["exchange"] == "binance"
    assert trades.json()["items"][0]["price"] == 50050.0

    pipeline = client.get(
        "/ops/pipeline/health",
        headers=_auth_headers(viewer),
        params={"mode": "MOCK"},
    )
    assert pipeline.status_code == 200
    payload = pipeline.json()
    assert payload["mode_filter"] == "MOCK"
    stage_by_name = {item["stage"]: item for item in payload["stages"]}
    assert stage_by_name["market.klines"]["records_total"] >= 1
    assert stage_by_name["market.orderbook"]["records_total"] >= 1
    assert stage_by_name["trading.fills"]["records_total"] >= 1
    assert stage_by_name["portfolio.snapshots"]["records_total"] >= 1
