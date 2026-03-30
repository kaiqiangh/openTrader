from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.api.dependencies import get_api_settings
from services.api.models import AuthPrincipal, UserRole
from services.api.settings import APISettings

_bearer = HTTPBearer(auto_error=False)


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: APISettings = Depends(get_api_settings),
) -> AuthPrincipal:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth scheme")
    return _decode_and_validate_token(token=credentials.credentials, settings=settings)


def require_roles(*allowed_roles: UserRole) -> Callable[[AuthPrincipal], AuthPrincipal]:
    allowed = {role.value for role in allowed_roles}

    async def _require(principal: AuthPrincipal = Depends(get_current_principal)) -> AuthPrincipal:
        if principal.role.value not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return principal

    return _require


require_viewer = require_roles(UserRole.VIEWER, UserRole.OPERATOR, UserRole.ADMIN)
require_operator = require_roles(UserRole.OPERATOR, UserRole.ADMIN)
require_admin = require_roles(UserRole.ADMIN)


def _decode_and_validate_token(*, token: str, settings: APISettings) -> AuthPrincipal:
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed JWT")

    header_segment, payload_segment, signature_segment = parts
    try:
        header = json.loads(_b64url_decode(header_segment))
        payload = json.loads(_b64url_decode(payload_segment))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT encoding") from exc

    # NOTE: JWT Algorithm — HS256 (HMAC-SHA256)
    # HS256 is used because the current codebase signs and verifies JWTs with a single shared secret.
    # Trade-off: symmetric signing means any holder of the secret can forge tokens. For production
    # deployments with multiple services, RS256 (asymmetric) or ES256 (ECDSA) would provide better
    # separation of concerns — signing keys stay with the issuer, verification keys are public.
    # TODO: migrate to RS256/ES256 when multi-service token issuance is needed.
    algorithm = str(header.get("alg", ""))
    if algorithm != "HS256":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unsupported JWT algorithm")

    signing_input = f"{header_segment}.{payload_segment}".encode("utf-8")
    expected_signature = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    received_signature = _b64url_decode_bytes(signature_segment)
    if not hmac.compare_digest(expected_signature, received_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT signature")

    _validate_registered_claims(payload=payload, settings=settings)

    subject = str(payload.get("sub", "")).strip()
    role = str(payload.get("role", "")).strip().lower()
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT missing sub claim")
    if role not in {item.value for item in UserRole}:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT has invalid role claim")

    return AuthPrincipal(user_id=subject, role=UserRole(role))


def _validate_registered_claims(*, payload: dict[str, object], settings: APISettings) -> None:
    now = int(datetime.now(timezone.utc).timestamp())

    exp = payload.get("exp")
    if exp is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT missing exp claim")
    if not isinstance(exp, (int, float)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT exp claim must be numeric")
    if int(exp) <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT expired")

    # Enforce maximum token lifetime to limit the blast radius of a leaked token.
    # Uses `iat` (issued-at) if present, otherwise falls back to `nbf` (not-before).
    iat = payload.get("iat")
    not_before = payload.get("nbf")
    issued_at = iat if isinstance(iat, (int, float)) else not_before if isinstance(not_before, (int, float)) else None
    if issued_at is not None:
        lifetime_seconds = int(exp) - int(issued_at)
        max_lifetime_seconds = settings.jwt_max_lifetime_hours * 3600
        if lifetime_seconds > max_lifetime_seconds:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="JWT lifetime exceeds maximum allowed",
            )

    nbf = payload.get("nbf")
    if nbf is not None and isinstance(nbf, (int, float)) and int(nbf) > now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT not active yet")

    issuer = payload.get("iss")
    if issuer is not None and str(issuer) != settings.jwt_issuer:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT issuer mismatch")

    audience = payload.get("aud")
    if audience is None:
        return
    if isinstance(audience, str) and audience == settings.jwt_audience:
        return
    if isinstance(audience, list) and settings.jwt_audience in audience:
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT audience mismatch")


def _b64url_decode(segment: str) -> str:
    return _b64url_decode_bytes(segment).decode("utf-8")


def _b64url_decode_bytes(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    try:
        return base64.urlsafe_b64decode(segment + padding)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT segment") from exc
