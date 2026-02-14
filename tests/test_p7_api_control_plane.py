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


def test_liveness_and_readiness_endpoints_are_public() -> None:
    settings = _settings()
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)

    liveness = client.get("/health/liveness")
    readiness = client.get("/health/readiness")

    assert liveness.status_code == 200
    assert liveness.json()["status"] == "ok"
    assert readiness.status_code == 200
    assert readiness.json()["status"] == "ready"


def test_metadata_requires_authentication() -> None:
    settings = _settings()
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)

    response = client.get("/metadata")
    assert response.status_code == 401


def test_viewer_can_read_control_endpoints() -> None:
    settings = _settings()
    token = _encode_jwt(subject="viewer-user", role="viewer", settings=settings)
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)

    mode_response = client.get("/control/mode", headers=_auth_headers(token))
    strategies_response = client.get("/control/strategies", headers=_auth_headers(token))

    assert mode_response.status_code == 200
    assert mode_response.json()["mode"] == "MOCK"
    assert strategies_response.status_code == 200
    assert isinstance(strategies_response.json()["items"], list)


def test_viewer_cannot_update_mode_but_operator_can() -> None:
    settings = _settings()
    viewer_token = _encode_jwt(subject="viewer-user", role="viewer", settings=settings)
    operator_token = _encode_jwt(subject="operator-user", role="operator", settings=settings)
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


def test_operator_can_update_strategy_state() -> None:
    settings = _settings()
    token = _encode_jwt(subject="operator-user", role="operator", settings=settings)
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
