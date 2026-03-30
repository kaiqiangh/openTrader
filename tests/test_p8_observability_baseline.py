from __future__ import annotations

import json

from fastapi.testclient import TestClient

from services.api.app import create_app
from services.api.settings import APISettings
from services.api.state import build_default_state
from services.shared.runtime.structured_logging import StructuredLogger
from services.shared.runtime.trace_context import build_traceparent, parse_traceparent
from tests.jwt_test_helpers import encode_jwt_rs256, make_test_settings


def _settings() -> APISettings:
    return make_test_settings()


def test_structured_logger_emits_required_schema() -> None:
    captured: list[str] = []
    logger = StructuredLogger(service="api", sink=captured.append)
    logger.info(
        event="http.request.completed",
        trace_id="trace-1",
        decision_id="decision-1",
        strategy_id="btc-momentum",
        mode="MOCK",
        context={"status_code": 200},
    )

    assert len(captured) == 1
    payload = json.loads(captured[0])
    assert payload["service"] == "api"
    assert payload["event"] == "http.request.completed"
    assert payload["level"] == "INFO"
    assert payload["trace_id"] == "trace-1"
    assert payload["decision_id"] == "decision-1"
    assert payload["strategy_id"] == "btc-momentum"
    assert payload["mode"] == "MOCK"
    assert "timestamp" in payload


def test_api_metrics_endpoint_and_trace_headers() -> None:
    settings = _settings()
    token = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)
    app = create_app(
        settings=settings, state=build_default_state(default_mode=settings.default_mode)
    )
    client = TestClient(app)

    incoming = build_traceparent(trace_id="0123456789abcdef0123456789abcdef")
    liveness = client.get("/health/liveness", headers={"traceparent": incoming})
    assert liveness.status_code == 200
    assert "traceparent" in liveness.headers
    assert liveness.headers["x-trace-id"] == "0123456789abcdef0123456789abcdef"
    assert parse_traceparent(liveness.headers["traceparent"]) is not None

    _ = client.get("/metadata", headers={"Authorization": f"Bearer {token}"})
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    body = metrics.text
    assert "open_trader_http_requests_total" in body
    assert 'service="api"' in body
    assert "open_trader_http_request_duration_seconds_bucket" in body
