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


def test_notification_observability_ops_endpoints_expose_metrics_deliveries_and_traces() -> None:
    settings = _settings()
    app = create_app(
        settings=settings, state=build_default_state(default_mode=settings.default_mode)
    )
    client = TestClient(app)
    token = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)

    metrics = client.get("/ops/notifications/metrics", headers=_auth_headers(token))
    deliveries = client.get("/ops/notifications/deliveries", headers=_auth_headers(token))
    traces = client.get("/ops/notifications/traces", headers=_auth_headers(token))

    assert metrics.status_code == 200
    assert deliveries.status_code == 200
    assert traces.status_code == 200

    assert metrics.json()["totals"]["received_total"] >= 1
    assert len(deliveries.json()["items"]) >= 1
    assert len(traces.json()["items"]) >= 1
