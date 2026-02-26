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


def test_dashboard_routes_show_migration_notice() -> None:
    settings = _settings()
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)
    token = _encode_jwt(subject="viewer-user", role="viewer", settings=settings)

    governance = client.get("/dashboard/governance", headers=_auth_headers(token))
    replay = client.get("/dashboard/replay", headers=_auth_headers(token))
    mode = client.get("/dashboard/mode", headers=_auth_headers(token))
    news = client.get("/dashboard/news", headers=_auth_headers(token))
    notifications = client.get("/dashboard/notifications", headers=_auth_headers(token))

    assert governance.status_code == 200
    assert "legacy API-served dashboard has been removed" in governance.text
    assert "http://localhost:3000/governance" in governance.text

    assert replay.status_code == 200
    assert "http://localhost:3000/replay" in replay.text

    assert mode.status_code == 200
    assert "http://localhost:3000/mode" in mode.text
    assert news.status_code == 200
    assert "http://localhost:3000/news" in news.text
    assert notifications.status_code == 200
    assert "http://localhost:3000/notifications" in notifications.text


def test_legacy_dashboard_static_assets_are_not_served() -> None:
    settings = _settings()
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)

    js = client.get("/static/dashboard_app.js")
    css = client.get("/static/dashboard.css")

    assert js.status_code == 404
    assert css.status_code == 404
