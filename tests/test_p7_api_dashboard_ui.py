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

def test_dashboard_routes_show_migration_notice() -> None:
    settings = _settings()
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)
    token = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)

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
