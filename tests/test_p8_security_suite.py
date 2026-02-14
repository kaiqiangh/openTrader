from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from services.api.app import create_app
from services.api.settings import APISettings
from services.api.state import build_default_state
from services.shared.runtime.exchange_credentials import EncryptedExchangeCredentialStore
from services.shared.runtime.key_encryption import AesGcmKeyEncryptor


def _encode_jwt(*, subject: str, role: str, settings: APISettings, iss: str | None = None, aud: str | None = None) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "role": role,
        "iss": iss if iss is not None else settings.jwt_issuer,
        "aud": aud if aud is not None else settings.jwt_audience,
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp()),
    }
    encoded_header = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    signature = hmac.new(settings.jwt_secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_b64url(signature)}"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("utf-8")


def _settings() -> APISettings:
    return APISettings(
        app_name="open-trader",
        app_version="0.1.0",
        default_mode="MOCK",
        jwt_secret_key="test-secret-key",
        jwt_issuer="open-trader-tests",
        jwt_audience="open-trader-api",
    )


def test_jwt_issuer_mismatch_is_rejected() -> None:
    settings = _settings()
    token = _encode_jwt(
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
    token = _encode_jwt(
        subject="viewer-user",
        role="viewer",
        settings=settings,
        aud="unexpected-audience",
    )
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)

    response = client.get("/metadata", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_encrypted_exchange_credentials_are_not_plaintext_at_rest() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE exchanges (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            api_key_encrypted TEXT,
            api_secret_encrypted TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    key = base64.b64encode(os.urandom(32)).decode("utf-8")
    store = EncryptedExchangeCredentialStore(
        connection=connection,
        encryptor=AesGcmKeyEncryptor(encryption_key_base64=key),
    )
    store.upsert_credentials(exchange_name="binance", api_key="plain-key", api_secret="plain-secret")

    row = connection.execute(
        "SELECT api_key_encrypted, api_secret_encrypted FROM exchanges WHERE name = ?",
        ("binance",),
    ).fetchone()
    assert row is not None
    assert "plain-key" not in str(row["api_key_encrypted"])
    assert "plain-secret" not in str(row["api_secret_encrypted"])


def test_security_suite_has_runbook_references() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "docs/runbooks/exchange-outage.md" in readme
    assert "docs/runbooks/llm-quota-breach.md" in readme
    assert "docs/runbooks/risk-incident.md" in readme

