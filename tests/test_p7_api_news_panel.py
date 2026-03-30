from __future__ import annotations


from fastapi.testclient import TestClient

from services.api.app import create_app
from services.api.settings import APISettings
from services.api.state import build_default_state
from tests.jwt_test_helpers import encode_jwt_rs256, make_test_settings


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _settings() -> APISettings:
    return make_test_settings()


def test_news_ops_endpoints_expose_items_summaries_and_impact() -> None:
    settings = _settings()
    app = create_app(
        settings=settings, state=build_default_state(default_mode=settings.default_mode)
    )
    client = TestClient(app)
    token = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)

    items = client.get("/ops/news/items", headers=_auth_headers(token))
    summaries = client.get("/ops/news/summaries", headers=_auth_headers(token))
    impact = client.get("/ops/news/impact", headers=_auth_headers(token))

    assert items.status_code == 200
    assert summaries.status_code == 200
    assert impact.status_code == 200

    assert len(items.json()["items"]) >= 1
    assert len(summaries.json()["items"]) >= 1
    assert len(impact.json()["items"]) >= 1


def test_dashboard_news_route_points_to_next_dashboard() -> None:
    settings = _settings()
    app = create_app(
        settings=settings, state=build_default_state(default_mode=settings.default_mode)
    )
    client = TestClient(app)
    token = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)

    response = client.get("/dashboard/news", headers=_auth_headers(token))

    assert response.status_code == 200
    assert "legacy API-served dashboard has been removed" in response.text
    assert "http://localhost:3000/news" in response.text
