from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
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


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("utf-8")


def _encode_jwt(*, subject: str, role: str, settings: APISettings) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "role": role,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp()),
    }
    encoded_header = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    signature = hmac.new(settings.jwt_secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_b64url(signature)}"


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _settings() -> APISettings:
    return APISettings(
        app_name="open-trader",
        app_version="0.1.0",
        default_mode="MOCK",
        jwt_secret_key="test-secret-key",
        jwt_issuer="open-trader-tests",
        jwt_audience="open-trader-api",
        read_only_mode=False,
    )


def _repository(tmp_path) -> ControlPlaneRepository:
    db_path = tmp_path / "runtime_truth.db"
    engine = create_engine(f"sqlite+pysqlite:///{db_path}", future=True)
    return ControlPlaneRepository(engine=engine)


def test_control_mode_and_strategy_changes_are_restart_safe(tmp_path) -> None:
    settings = _settings()
    repo = _repository(tmp_path)
    operator = _encode_jwt(subject="operator-user", role="operator", settings=settings)
    viewer = _encode_jwt(subject="viewer-user", role="viewer", settings=settings)

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
    admin = _encode_jwt(subject="admin-user", role="admin", settings=settings)
    viewer = _encode_jwt(subject="viewer-user", role="viewer", settings=settings)

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
    viewer = _encode_jwt(subject="viewer-user", role="viewer", settings=settings)

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
                    realized_pnl_today REAL NOT NULL
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
                "bids": "[{\"price\":50049.0,\"amount\":1.5}]",
                "asks": "[{\"price\":50051.0,\"amount\":1.2}]",
                "best_bid": 50049.0,
                "best_ask": 50051.0,
                "spread_bps": 0.399,
            },
        )

        connection.execute(
            text(
                """
                INSERT INTO portfolio_snapshots(snapshot_time, mode, total_balance_usd, available_balance_usd, locked_balance_usd, unrealized_pnl, realized_pnl_today)
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
