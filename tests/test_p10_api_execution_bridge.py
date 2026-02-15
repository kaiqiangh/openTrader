from __future__ import annotations

from fastapi.testclient import TestClient

from services.api.app import create_app
from services.api.settings import APISettings
from services.api.state import build_default_state


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
        "symbol": "BTC/USDT",
        "quantity": 0.1,
        "reduce_only": False,
        "idempotency_key": "idem-1",
        "client_order_id": "client-1",
        "exchange_order_id": "",
        "trace_id": "trace-1",
        "decision_id": "decision-1",
    }


def test_internal_execution_dispatch_accepts_valid_payload_without_key(monkeypatch) -> None:
    monkeypatch.delenv("REAL_EXECUTION_BRIDGE_API_KEY", raising=False)
    app = create_app(settings=_settings(), state=build_default_state(default_mode="MOCK"))
    client = TestClient(app)

    response = client.post("/internal/execution/dispatch", json=_bridge_payload())

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
