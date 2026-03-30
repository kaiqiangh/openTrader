from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from services.api.app import create_app
from services.api.settings import APISettings
from services.api.state import build_default_state
from tests.jwt_test_helpers import encode_jwt_rs256, make_test_settings

def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

def _settings() -> APISettings:
    return make_test_settings()

def test_liveness_is_public_readiness_requires_auth() -> None:
    settings = _settings()
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)

    liveness = client.get("/health/liveness")
    readiness = client.get("/health/readiness")

    assert liveness.status_code == 200
    assert liveness.json()["status"] == "ok"
    # Readiness now requires authentication (security hardening)
    assert readiness.status_code == 401

def test_metadata_requires_authentication() -> None:
    settings = _settings()
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)

    response = client.get("/metadata")
    assert response.status_code == 401

def test_viewer_can_read_control_endpoints() -> None:
    settings = _settings()
    token = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)

    mode_response = client.get("/control/mode", headers=_auth_headers(token))
    mode_history_response = client.get("/control/mode/history", headers=_auth_headers(token))
    strategies_response = client.get("/control/strategies", headers=_auth_headers(token))

    assert mode_response.status_code == 200
    assert mode_response.json()["mode"] == "MOCK"
    assert mode_history_response.status_code == 200
    assert isinstance(mode_history_response.json()["items"], list)
    assert strategies_response.status_code == 200
    assert isinstance(strategies_response.json()["items"], list)

def test_viewer_cannot_update_mode_but_operator_can() -> None:
    settings = _settings()
    viewer_token = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)
    operator_token = encode_jwt_rs256(subject="operator-user", role="operator", settings=settings)
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)

    viewer_attempt = client.put(
        "/control/mode",
        headers=_auth_headers(viewer_token),
        json={"mode": "REAL", "reason": "switch for validation"},
    )
    assert viewer_attempt.status_code == 403

    operator_attempt = client.put(
        "/control/mode",
        headers=_auth_headers(operator_token),
        json={"mode": "REAL", "reason": "switch for validation"},
    )
    assert operator_attempt.status_code == 200
    assert operator_attempt.json()["mode"] == "REAL"
    assert operator_attempt.json()["changed_by"] == "operator-user"

    mode_history = client.get("/control/mode/history", headers=_auth_headers(viewer_token))
    assert mode_history.status_code == 200
    assert mode_history.json()["items"][0]["mode"] == "REAL"
    assert mode_history.json()["items"][0]["reason"] == "switch for validation"

def test_operator_can_update_strategy_state() -> None:
    settings = _settings()
    token = encode_jwt_rs256(subject="operator-user", role="operator", settings=settings)
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)

    response = client.put(
        "/control/strategies/btc-momentum/state",
        headers=_auth_headers(token),
        json={"state": "DISABLED", "reason": "maintenance"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["strategy_id"] == "btc-momentum"
    assert payload["state"] == "DISABLED"
    assert payload["changed_by"] == "operator-user"
