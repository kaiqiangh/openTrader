from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi.testclient import TestClient

from services.api.app import create_app
from services.api.settings import APISettings
from services.api.state import build_default_state
from tests.jwt_test_helpers import encode_jwt_rs256, make_test_settings

def _settings() -> APISettings:
    return make_test_settings()

def test_jwt_issuer_mismatch_is_rejected() -> None:
    settings = _settings()
    token = encode_jwt_rs256(
        subject="viewer-user",
        role="viewer",
        settings=settings,
        iss="unexpected-issuer",
    )
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)

    response = client.get("/metadata", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401

def test_jwt_audience_mismatch_is_rejected() -> None:
    settings = _settings()
    token = encode_jwt_rs256(
        subject="viewer-user",
        role="viewer",
        settings=settings,
        aud="unexpected-audience",
    )
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)

    response = client.get("/metadata", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401

def test_security_suite_has_runbook_references() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "docs/runbooks/exchange-outage.md" in readme
    assert "docs/runbooks/llm-quota-breach.md" in readme
    assert "docs/runbooks/risk-incident.md" in readme

