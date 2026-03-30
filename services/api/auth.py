from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import jwt
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
    # SEC-026: When RS256 is configured (public key present), ONLY accept RS256.
    # No HS256 fallback — prevents algorithm confusion attacks.
    # HS256 path only runs when public key is absent AND secret key is set.
    if settings.jwt_public_key:
        algorithms = ["RS256"]
        key = settings.jwt_public_key
    elif settings.jwt_secret_key:
        algorithms = ["HS256"]
        key = settings.jwt_secret_key
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No JWT key configured",
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT audience mismatch")
    except jwt.InvalidSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT signature")
    except jwt.DecodeError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed JWT")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT encoding")

    # Enforce maximum token lifetime to limit the blast radius of a leaked token.
    _validate_token_lifetime(payload=payload, settings=settings)

    # Validate not-before if present.
    now = int(datetime.now(timezone.utc).timestamp())
    nbf = payload.get("nbf")
    if nbf is not None and isinstance(nbf, (int, float)) and int(nbf) > now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT not active yet")

    subject = str(payload.get("sub", "")).strip()
    role = str(payload.get("role", "")).strip().lower()
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT missing sub claim")
    if role not in {item.value for item in UserRole}:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT has invalid role claim")

    return AuthPrincipal(user_id=subject, role=UserRole(role))


def _validate_token_lifetime(*, payload: dict[str, object], settings: APISettings) -> None:
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        return

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
