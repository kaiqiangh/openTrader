from __future__ import annotations


from fastapi.testclient import TestClient

from services.api.app import create_app
from services.api.settings import APISettings
from services.api.state import build_default_state
from services.oms import PortfolioSnapshot, PositionState, ReconciliationOrder
from tests.jwt_test_helpers import encode_jwt_rs256, make_test_settings


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _settings() -> APISettings:
    return make_test_settings()


def test_ops_endpoints_return_orders_positions_snapshot_and_risk_status() -> None:
    settings = _settings()
    state = build_default_state(default_mode="MOCK")
    state.orders = [
        ReconciliationOrder(
            order_id="ord-1",
            symbol="BTC/USDT",
            mode="MOCK",
            requested_quantity=0.2,
            status="OPEN",
            filled_quantity=0.0,
        ),
    ]
    state.positions = [
        PositionState(
            mode="MOCK",
            symbol="BTC/USDT",
            quantity=0.2,
            average_entry_price=42000.0,
            realized_pnl=10.0,
            status="OPEN",
            updated_at="2026-02-14T19:00:00Z",
        )
    ]
    state.portfolio_snapshots = [
        PortfolioSnapshot(
            snapshot_time="2026-02-14T19:01:00Z",
            mode="MOCK",
            total_balance_usd=100200.0,
            available_balance_usd=99500.0,
            locked_balance_usd=700.0,
            unrealized_pnl=200.0,
            realized_pnl_total=10.0,
        )
    ]
    app = create_app(settings=settings, state=state)
    client = TestClient(app)
    viewer_token = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)

    orders_response = client.get("/ops/orders", headers=_auth_headers(viewer_token))
    positions_response = client.get("/ops/positions", headers=_auth_headers(viewer_token))
    snapshot_response = client.get("/ops/portfolio/latest", headers=_auth_headers(viewer_token))
    risk_response = client.get("/ops/risk/status", headers=_auth_headers(viewer_token))

    assert orders_response.status_code == 200
    assert orders_response.json()["items"][0]["order_id"] == "ord-1"
    assert positions_response.status_code == 200
    assert positions_response.json()["items"][0]["symbol"] == "BTC/USDT"
    assert snapshot_response.status_code == 200
    assert snapshot_response.json()["mode"] == "MOCK"
    assert risk_response.status_code == 200
    assert "kill_switch_enabled" in risk_response.json()


def test_operator_can_trip_and_reset_circuit_breaker() -> None:
    settings = _settings()
    app = create_app(settings=settings, state=build_default_state(default_mode="MOCK"))
    client = TestClient(app)
    operator_token = encode_jwt_rs256(subject="operator-user", role="operator", settings=settings)

    trip_response = client.post(
        "/ops/risk/circuit-breaker/trip",
        headers=_auth_headers(operator_token),
        json={"reason": "manual protection", "cooldown_seconds": 30},
    )
    assert trip_response.status_code == 200
    assert trip_response.json()["control"] == "circuit_breaker"
    assert trip_response.json()["status"] == "OPEN"

    reset_response = client.post(
        "/ops/risk/circuit-breaker/reset",
        headers=_auth_headers(operator_token),
        json={"reason": "manual reset"},
    )
    assert reset_response.status_code == 200
    assert reset_response.json()["status"] == "CLOSED"


def test_only_admin_can_toggle_kill_switch() -> None:
    settings = _settings()
    app = create_app(settings=settings, state=build_default_state(default_mode="MOCK"))
    client = TestClient(app)
    operator_token = encode_jwt_rs256(subject="operator-user", role="operator", settings=settings)
    admin_token = encode_jwt_rs256(subject="admin-user", role="admin", settings=settings)

    forbidden_response = client.post(
        "/ops/risk/kill-switch/enable",
        headers=_auth_headers(operator_token),
        json={"reason": "operator request"},
    )
    assert forbidden_response.status_code == 403

    admin_response = client.post(
        "/ops/risk/kill-switch/enable",
        headers=_auth_headers(admin_token),
        json={"reason": "admin emergency stop"},
    )
    assert admin_response.status_code == 200
    assert admin_response.json()["control"] == "kill_switch"
    assert admin_response.json()["status"] == "ENABLED"
