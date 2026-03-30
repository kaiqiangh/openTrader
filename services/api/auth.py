from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.api.dependencies import get_api_settings
from services.api.models import AuthPrincipal, UserRole
from services.api.settings import APISettings

_logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

# ── Refresh Token Support ────────────────────────────────────────────────────

_ACCESS_TOKEN_LIFETIME_MINUTES = 15
_REFRESH_TOKEN_LIFETIME_DAYS = 7


def generate_token_pair(
    *,
    user_id: str,
    role: str,
    settings: APISettings,
) -> dict[str, str]:
    """Generate an access + refresh token pair.

    Returns dict with 'access_token' and 'refresh_token' (both JWT strings).
    The access token is short-lived (15 min). The refresh token is long-lived (7 days)
    and can only be used to obtain new access tokens, not for API access.
    """
    if not settings.jwt_private_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No JWT private key configured — cannot generate tokens",
        )

    now = datetime.now(timezone.utc)
    jti = uuid.uuid4().hex

    # Access token — short-lived, for API authentication
    access_payload = {
        "sub": user_id,
        "role": role,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=_ACCESS_TOKEN_LIFETIME_MINUTES)).timestamp()),
        "jti": jti,
        "type": "access",
    }
    access_token = jwt.encode(access_payload, settings.jwt_private_key, algorithm="RS256")

    # Refresh token — long-lived, only for obtaining new access tokens
    refresh_jti = uuid.uuid4().hex
    refresh_payload = {
        "sub": user_id,
        "role": role,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=_REFRESH_TOKEN_LIFETIME_DAYS)).timestamp()),
        "jti": refresh_jti,
        "type": "refresh",
        "access_jti": jti,  # links to the access token it was issued with
    }
    refresh_token = jwt.encode(refresh_payload, settings.jwt_private_key, algorithm="RS256")

    # Store refresh JTI in Redis for revocation support (optional)
    _store_refresh_jti(refresh_jti, _REFRESH_TOKEN_LIFETIME_DAYS * 86400)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": _ACCESS_TOKEN_LIFETIME_MINUTES * 60,
    }


def refresh_access_token(*, refresh_token: str, settings: APISettings) -> dict[str, str]:
    """Validate a refresh token and issue a new access token.

    The refresh token must be valid, not expired, and not revoked.
    Returns a new token pair (access + refresh) — token rotation.
    """
    if not settings.jwt_public_key or not settings.jwt_private_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT keys not configured",
        )

    # Decode refresh token
    try:
        payload = jwt.decode(
            refresh_token,
            settings.jwt_public_key,
            algorithms=["RS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["exp", "sub", "type", "jti"], "verify_exp": True},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired"
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid refresh token: {exc}"
        )

    # Verify it's a refresh token
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token is not a refresh token"
        )

    # Check revocation
    jti = str(payload.get("jti", ""))
    if _is_jti_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been revoked"
        )

    # Issue new token pair (rotation — old refresh token is revoked)
    _revoke_jti(jti)

    return generate_token_pair(
        user_id=str(payload["sub"]),
        role=str(payload.get("role", "viewer")),
        settings=settings,
    )


def _store_refresh_jti(jti: str, ttl_seconds: int) -> None:
    """Store refresh token JTI in Redis for revocation tracking. Best-effort."""
    try:
        import redis as redis_lib

        redis_url = os.getenv("REDIS_URL", "").strip()
        if not redis_url:
            return
        client = redis_lib.from_url(redis_url, decode_responses=True)
        client.setex(f"jwt:refresh:{jti}", ttl_seconds, "1")
    except Exception:
        pass  # Best-effort — revocation won't work without Redis


def _is_jti_revoked(jti: str) -> bool:
    """Check if a JTI has been revoked. Best-effort (assumes not revoked if Redis unavailable)."""
    try:
        import redis as redis_lib

        redis_url = os.getenv("REDIS_URL", "").strip()
        if not redis_url:
            return False
        client = redis_lib.from_url(redis_url, decode_responses=True)
        return client.exists(f"jwt:revoked:{jti}") > 0
    except Exception:
        return False


def _revoke_jti(jti: str) -> None:
    """Mark a JTI as revoked in Redis. Best-effort."""
    try:
        import redis as redis_lib

        redis_url = os.getenv("REDIS_URL", "").strip()
        if not redis_url:
            return
        client = redis_lib.from_url(redis_url, decode_responses=True)
        # Set with 8-day TTL (longer than refresh token lifetime)
        client.setex(f"jwt:revoked:{jti}", 8 * 86400, "1")
    except Exception:
        pass


# ── Token Verification ───────────────────────────────────────────────────────


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
    # SEC-026: Only RS256 — no HS256 fallback prevents algorithm confusion attacks.
    if settings.jwt_public_key:
        algorithms = ["RS256"]
        key = settings.jwt_public_key
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No JWT public key configured — RS256 verification required",
        )
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={
                "require": ["exp", "sub"],
                "verify_exp": True,
                "verify_iss": True,
                "verify_aud": True,
            },
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT expired")
    except jwt.InvalidIssuerError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT issuer mismatch")
    except jwt.InvalidAudienceError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT audience mismatch"
        )
    except jwt.InvalidSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT signature"
        )
    except jwt.DecodeError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed JWT")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT encoding")

    # Enforce maximum token lifetime to limit the blast radius of a leaked token.
    _validate_token_lifetime(payload=payload, settings=settings)

    # T9: Warn on tokens with lifetime > 900s (15 min) — encourages short-lived tokens.
    _warn_if_long_lived(payload=payload)

    # Validate not-before if present.
    now = int(datetime.now(timezone.utc).timestamp())
    nbf = payload.get("nbf")
    if nbf is not None and isinstance(nbf, (int, float)) and int(nbf) > now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT not active yet")

    subject = str(payload.get("sub", "")).strip()
    role = str(payload.get("role", "")).strip().lower()
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT missing sub claim"
        )
    if role not in {item.value for item in UserRole}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT has invalid role claim"
        )

    # Only accept access tokens for API authentication (not refresh tokens)
    token_type = payload.get("type", "access")
    if token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh tokens cannot be used for API access",
        )

    # Check if token has been revoked
    jti = payload.get("jti")
    if jti and _is_jti_revoked(str(jti)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked"
        )

    return AuthPrincipal(user_id=subject, role=UserRole(role))


def _validate_token_lifetime(*, payload: dict[str, object], settings: APISettings) -> None:
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        return

    iat = payload.get("iat")
    not_before = payload.get("nbf")
    issued_at = (
        iat
        if isinstance(iat, (int, float))
        else not_before
        if isinstance(not_before, (int, float))
        else None
    )
    if issued_at is not None:
        lifetime_seconds = int(exp) - int(issued_at)
        max_lifetime_seconds = settings.jwt_max_lifetime_hours * 3600
        if lifetime_seconds > max_lifetime_seconds:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="JWT lifetime exceeds maximum allowed",
            )


def _warn_if_long_lived(*, payload: dict[str, object]) -> None:
    """T9: Log warning for tokens with lifetime > 900s (15 min). Encourages short-lived tokens."""
    exp = payload.get("exp")
    iat = payload.get("iat")
    not_before = payload.get("nbf")
    issued_at = (
        iat
        if isinstance(iat, (int, float))
        else not_before
        if isinstance(not_before, (int, float))
        else None
    )
    if isinstance(exp, (int, float)) and isinstance(issued_at, (int, float)):
        lifetime_seconds = int(exp) - int(issued_at)
        if lifetime_seconds > 900:
            subject = payload.get("sub", "unknown")
            _logger.warning(
                "Long-lived JWT detected: sub=%s lifetime_seconds=%d (recommend < 900s)",
                subject,
                lifetime_seconds,
            )
