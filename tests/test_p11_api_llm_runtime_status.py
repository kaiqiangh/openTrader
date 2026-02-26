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
        llm_runtime_enabled=True,
        litellm_base_url="http://litellm:4000",
        llm_quick_provider_order=("openai", "anthropic"),
        llm_deep_provider_order=("anthropic", "openai"),
    )


def test_llm_runtime_status_endpoint_reflects_runtime_settings() -> None:
    settings = _settings()
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)
    token = _encode_jwt(subject="viewer-user", role="viewer", settings=settings)

    response = client.get("/ops/llm/runtime", headers=_auth_headers(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime_enabled"] is True
    assert payload["litellm_base_url_configured"] is True
    assert payload["quick_provider_order"] == ["openai", "anthropic"]
    assert payload["deep_provider_order"] == ["anthropic", "openai"]
    assert payload["total_calls"] >= 0
    assert payload["succeeded_calls"] >= 0
    assert payload["failed_calls"] >= 0
