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

def test_notification_preference_crud_and_rbac() -> None:
    settings = _settings()
    app = create_app(settings=settings, state=build_default_state(default_mode="MOCK"))
    client = TestClient(app)
    viewer_token = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)
    operator_token = encode_jwt_rs256(subject="operator-user", role="operator", settings=settings)
    admin_token = encode_jwt_rs256(subject="admin-user", role="admin", settings=settings)

    list_response = client.get("/ops/notifications/preferences", headers=_auth_headers(viewer_token))
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) >= 1

    forbidden_response = client.put(
        "/ops/notifications/preferences/ops-1",
        headers=_auth_headers(operator_token),
        json={"min_severity": "WARNING", "gateways": ["telegram"]},
    )
    assert forbidden_response.status_code == 403

    upsert_response = client.put(
        "/ops/notifications/preferences/ops-1",
        headers=_auth_headers(admin_token),
        json={
            "min_severity": "CRITICAL",
            "gateways": ["telegram", "webhook"],
            "strategy_ids": ["btc-momentum"],
            "event_types": ["notify.risk.event"],
        },
    )
    assert upsert_response.status_code == 200
    assert upsert_response.json()["user_id"] == "ops-1"
    assert upsert_response.json()["min_severity"] == "CRITICAL"

    filtered_response = client.get(
        "/ops/notifications/preferences",
        headers=_auth_headers(viewer_token),
        params={"user_id": "ops-1"},
    )
    assert filtered_response.status_code == 200
    assert len(filtered_response.json()["items"]) == 1

    delete_response = client.delete("/ops/notifications/preferences/ops-1", headers=_auth_headers(admin_token))
    assert delete_response.status_code == 204

def test_notification_preference_validation_rejects_empty_gateways() -> None:
    settings = _settings()
    app = create_app(settings=settings, state=build_default_state(default_mode="MOCK"))
    client = TestClient(app)
    admin_token = encode_jwt_rs256(subject="admin-user", role="admin", settings=settings)

    response = client.put(
        "/ops/notifications/preferences/ops-2",
        headers=_auth_headers(admin_token),
        json={"min_severity": "INFO", "gateways": []},
    )
    assert response.status_code == 422
