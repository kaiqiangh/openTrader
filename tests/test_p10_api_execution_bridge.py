from __future__ import annotations

from fastapi.testclient import TestClient

from services.api.app import create_app
from services.api.settings import APISettings
from services.api.state import build_default_state

_TEST_BRIDGE_KEY = "test-bridge-key"


def _settings() -> APISettings:
    return APISettings(
        app_name="open-trader",
        app_version="0.1.0",
        default_mode="MOCK",
        jwt_secret_key="test-secret-key",
        jwt_issuer="open-trader-tests",
        jwt_audience="open-trader-api",
    )


def _bridge_payload() -> dict[str, object]:
    return {
        "command_id": "cmd-1",
        "operation": "CREATE_ORDER",
        "action": "BUY",
        "exchange": "binance",
        "symbol": "BTC/USDT",
        "quantity": 0.1,
        "order_type": "MARKET",
        "time_in_force": None,
        "limit_price": None,
        "trigger_price": None,
        "reduce_only": False,
        "idempotency_key": "idem-1",
        "client_order_id": "client-1",
        "exchange_order_id": "",
        "trace_id": "trace-1",
        "decision_id": "decision-1",
    }


def _status_payload() -> dict[str, object]:
    payload = _bridge_payload()
    payload["operation"] = "GET_ORDER_STATUS"
    payload["action"] = "CANCEL"
    payload["quantity"] = 0.0
    payload["exchange_order_id"] = "123456789"
    return payload


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_TEST_BRIDGE_KEY}"}


def _app_with_bridge_key(monkeypatch) -> TestClient:
    monkeypatch.setenv("REAL_EXECUTION_BRIDGE_API_KEY", _TEST_BRIDGE_KEY)
    app = create_app(settings=_settings(), state=build_default_state(default_mode="MOCK"))
    return TestClient(app)


def test_internal_execution_dispatch_returns_503_when_no_bridge_key(monkeypatch) -> None:
    monkeypatch.delenv("REAL_EXECUTION_BRIDGE_API_KEY", raising=False)
    app = create_app(settings=_settings(), state=build_default_state(default_mode="MOCK"))
    client = TestClient(app)

    response = client.post("/internal/execution/dispatch", json=_bridge_payload())

    assert response.status_code == 503
    assert "REAL_EXECUTION_BRIDGE_API_KEY" in response.json()["detail"]


def test_internal_execution_dispatch_accepts_valid_payload_with_key(monkeypatch) -> None:
    client = _app_with_bridge_key(monkeypatch)
    response = client.post("/internal/execution/dispatch", json=_bridge_payload(), headers=_auth_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["order_id"] == "client-1"
    assert payload["status"] == "submitted"
    assert payload["raw_response"]["accepted"] is True


def test_internal_execution_dispatch_rejects_missing_authorization_when_key_configured(monkeypatch) -> None:
    monkeypatch.setenv("REAL_EXECUTION_BRIDGE_API_KEY", "bridge-key")
    app = create_app(settings=_settings(), state=build_default_state(default_mode="MOCK"))
    client = TestClient(app)

    response = client.post("/internal/execution/dispatch", json=_bridge_payload())

    assert response.status_code == 401


def test_internal_execution_dispatch_accepts_authorization_when_key_configured(monkeypatch) -> None:
    monkeypatch.setenv("REAL_EXECUTION_BRIDGE_API_KEY", "bridge-key")
    app = create_app(settings=_settings(), state=build_default_state(default_mode="MOCK"))
    client = TestClient(app)

    response = client.post(
        "/internal/execution/dispatch",
        json=_bridge_payload(),
        headers={"Authorization": "Bearer bridge-key"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "submitted"


def test_internal_execution_dispatch_rejects_missing_trigger_for_stop_market_order(monkeypatch) -> None:
    client = _app_with_bridge_key(monkeypatch)
    payload = _bridge_payload()
    payload["order_type"] = "STOP_MARKET"
    payload["trigger_price"] = None

    response = client.post("/internal/execution/dispatch", json=payload, headers=_auth_headers())

    assert response.status_code == 422
    assert "trigger_price must be positive" in response.json()["detail"]


def test_internal_execution_dispatch_status_operation_requires_order_identifier(monkeypatch) -> None:
    client = _app_with_bridge_key(monkeypatch)
    payload = _status_payload()
    payload["exchange_order_id"] = ""
    payload["client_order_id"] = None

    response = client.post("/internal/execution/dispatch", json=payload, headers=_auth_headers())

    assert response.status_code == 422
    assert "status operation requires exchange_order_id or client_order_id" in response.json()["detail"]


def test_internal_execution_dispatch_status_operation_returns_order_state(monkeypatch) -> None:
    client = _app_with_bridge_key(monkeypatch)
    response = client.post("/internal/execution/dispatch", json=_status_payload(), headers=_auth_headers())

    assert response.status_code == 200
    assert response.json()["status"] == "submitted"


def test_internal_execution_dispatch_rejects_real_mode_when_exchange_credentials_missing(monkeypatch) -> None:
    client = _app_with_bridge_key(monkeypatch)
    monkeypatch.setenv("INTERNAL_EXECUTION_REAL_DISPATCH", "true")
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)

    response = client.post("/internal/execution/dispatch", json=_bridge_payload(), headers=_auth_headers())

    assert response.status_code == 422
    assert "missing Binance credentials" in response.json()["detail"]
