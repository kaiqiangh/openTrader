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


def test_news_ops_endpoints_expose_items_summaries_and_impact() -> None:
    settings = _settings()
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)
    token = _encode_jwt(subject="viewer-user", role="viewer", settings=settings)

    items = client.get("/ops/news/items", headers=_auth_headers(token))
    summaries = client.get("/ops/news/summaries", headers=_auth_headers(token))
    impact = client.get("/ops/news/impact", headers=_auth_headers(token))

    assert items.status_code == 200
    assert summaries.status_code == 200
    assert impact.status_code == 200

    assert len(items.json()["items"]) >= 1
    assert len(summaries.json()["items"]) >= 1
    assert len(impact.json()["items"]) >= 1


def test_dashboard_news_route_renders_shell_marker() -> None:
    settings = _settings()
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)
    token = _encode_jwt(subject="viewer-user", role="viewer", settings=settings)

    response = client.get("/dashboard/news", headers=_auth_headers(token))

    assert response.status_code == 200
    assert "data-view='news'" in response.text
    assert "/ops/news/items" in client.get("/static/dashboard_app.js").text
