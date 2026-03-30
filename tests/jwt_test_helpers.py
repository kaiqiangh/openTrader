"""Shared RS256 JWT test helpers for SEC-009 migration.

Provides RSA key pair generation and JWT encoding with RS256 for tests.
All test files should import from here instead of hand-rolling HS256 tokens.
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from services.api.settings import APISettings

_TEST_PRIVATE_KEY: str | None = None
_TEST_PUBLIC_KEY: str | None = None


def get_test_rsa_keys() -> tuple[str, str]:
    """Return (private_pem, public_pem) — cached, generated once per process."""
    global _TEST_PRIVATE_KEY, _TEST_PUBLIC_KEY
    if _TEST_PRIVATE_KEY is None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        _TEST_PRIVATE_KEY = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        _TEST_PUBLIC_KEY = (
            private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )
    return _TEST_PRIVATE_KEY, _TEST_PUBLIC_KEY


def encode_jwt_rs256(
    *,
    subject: str,
    role: str,
    settings: APISettings,
    expires_in: timedelta = timedelta(minutes=30),
    **overrides: object,
) -> str:
    """Encode a JWT with RS256 using the test RSA private key.

    Pass **overrides to replace standard claims (iss, aud, exp, etc.).
    """
    private_key_pem, _ = get_test_rsa_keys()
    now = datetime.now(timezone.utc)
    payload: dict[str, object] = {
        "sub": subject,
        "role": role,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "exp": int((now + expires_in).timestamp()),
        "iat": int(now.timestamp()),
    }
    payload.update(overrides)
    return jwt.encode(payload, private_key_pem, algorithm="RS256")


def make_test_settings(**overrides: object) -> APISettings:
    """Create APISettings for tests with RS256 keys pre-filled.

    Pass any overrides to replace defaults. Example::

        settings = make_test_settings(app_name="my-app")
    """
    private_key_pem, public_key_pem = get_test_rsa_keys()
    defaults: dict[str, object] = dict(
        app_name="open-trader",
        app_version="0.1.0",
        default_mode="MOCK",
        jwt_secret_key="test-secret-key",  # legacy fallback
        jwt_issuer="open-trader-tests",
        jwt_audience="open-trader-api",
        jwt_private_key=private_key_pem,
        jwt_public_key=public_key_pem,
    )
    defaults.update(overrides)
    return APISettings(**defaults)  # type: ignore[arg-type]


def b64url(raw: bytes) -> str:
    """Base64url encode without padding."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("utf-8")
