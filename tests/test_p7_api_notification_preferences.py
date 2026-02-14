from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from services.api.app import create_app
from services.api.settings import APISettings
from services.api.state import build_default_state


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


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("utf-8")


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
    )


def test_notification_preference_crud_and_rbac() -> None:
    settings = _settings()
    app = create_app(settings=settings, state=build_default_state(default_mode="MOCK"))
    client = TestClient(app)
    viewer_token = _encode_jwt(subject="viewer-user", role="viewer", settings=settings)
    operator_token = _encode_jwt(subject="operator-user", role="operator", settings=settings)
    admin_token = _encode_jwt(subject="admin-user", role="admin", settings=settings)

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
    admin_token = _encode_jwt(subject="admin-user", role="admin", settings=settings)

    response = client.put(
        "/ops/notifications/preferences/ops-2",
        headers=_auth_headers(admin_token),
        json={"min_severity": "INFO", "gateways": []},
    )
    assert response.status_code == 422
