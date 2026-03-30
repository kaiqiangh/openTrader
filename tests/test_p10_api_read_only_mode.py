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


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("utf-8")


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


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _settings(*, read_only_mode: bool) -> APISettings:
    return APISettings(
        app_name="open-trader",
        app_version="0.1.0",
        default_mode="MOCK",
        jwt_secret_key="test-secret-key",
        jwt_issuer="open-trader-tests",
        jwt_audience="open-trader-api",
        read_only_mode=read_only_mode,
    )


def test_api_read_only_mode_blocks_non_internal_mutation_routes() -> None:
    settings = _settings(read_only_mode=True)
    token = _encode_jwt(subject="operator-user", role="operator", settings=settings)
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)

    response = client.put(
        "/control/mode",
        headers=_auth_headers(token),
        json={"mode": "REAL", "reason": "read-only verification"},
    )

    assert response.status_code == 403
    assert "read-only mode" in response.json()["detail"]


def test_api_read_only_mode_keeps_internal_bridge_mutation_routes_available(monkeypatch) -> None:
    monkeypatch.setenv("REAL_EXECUTION_BRIDGE_API_KEY", "test-bridge-key")
    settings = _settings(read_only_mode=True)
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)

    response = client.post(
        "/internal/execution/dispatch",
        headers={"Authorization": "Bearer test-bridge-key"},
        json={
            "command_id": "cmd-1",
            "operation": "CREATE_ORDER",
            "action": "BUY",
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "quantity": 0.01,
            "order_type": "MARKET",
            "time_in_force": None,
            "limit_price": None,
            "trigger_price": None,
            "reduce_only": False,
            "idempotency_key": "idem-1",
            "client_order_id": "client-1",
            "exchange_order_id": "",
            "trace_id": "trace-1",
            "decision_id": "decision-1",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
