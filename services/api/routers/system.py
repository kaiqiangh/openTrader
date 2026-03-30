from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from services.api.auth import (
    generate_token_pair,
    refresh_access_token,
    require_viewer,
)
from services.api.dependencies import get_api_settings, get_control_plane_state
from services.api.models import (
    AuthPrincipal,
    ExecutionMode,
    HealthResponse,
    MetadataResponse,
    ReadinessResponse,
    UserRole,
)
from services.api.settings import APISettings
from services.api.state import ControlPlaneState

router = APIRouter(tags=["system"])


@router.get("/health/liveness", response_model=HealthResponse)
def health_liveness() -> HealthResponse:
    return HealthResponse(status="ok", service="api", time=_utc_now_iso())


@router.get("/health/readiness", response_model=ReadinessResponse)
def health_readiness(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
) -> ReadinessResponse:
    return ReadinessResponse(
        status="ready",
        service="api",
        mode=ExecutionMode(state.mode),
        strategy_count=len(state.strategies),
        time=_utc_now_iso(),
    )


@router.get("/metadata", response_model=MetadataResponse)
def metadata(
    _: AuthPrincipal = Depends(require_viewer),
    settings: APISettings = Depends(get_api_settings),
    state: ControlPlaneState = Depends(get_control_plane_state),
) -> MetadataResponse:
    return MetadataResponse(
        app_name=settings.app_name,
        app_version=settings.app_version,
        mode=ExecutionMode(state.mode),
        roles_supported=[UserRole.VIEWER, UserRole.OPERATOR, UserRole.ADMIN],
        features=[
            "mode_control",
            "strategy_control",
            "orders_endpoint",
            "positions_endpoint",
            "portfolio_endpoint",
            "risk_controls",
        ],
        generated_at=_utc_now_iso(),
    )


# ── Auth Endpoints ───────────────────────────────────────────────────────────


class TokenRequest(BaseModel):
    user_id: str
    role: str = "viewer"


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/auth/token")
def create_token_pair(
    body: TokenRequest,
    settings: APISettings = Depends(get_api_settings),
) -> dict[str, Any]:
    """Generate an access + refresh token pair.

    Access token: 15 min lifetime, use for API authentication.
    Refresh token: 7 day lifetime, use to get new access tokens.
    """
    role = body.role.strip().lower()
    if role not in {item.value for item in UserRole}:
        return JSONResponse(status_code=400, content={"detail": f"Invalid role: {role}"})

    return generate_token_pair(user_id=body.user_id, role=role, settings=settings)


@router.post("/auth/refresh")
def refresh_token(
    body: RefreshRequest,
    settings: APISettings = Depends(get_api_settings),
) -> dict[str, Any]:
    """Exchange a refresh token for a new access + refresh token pair.

    Implements token rotation: the old refresh token is revoked.
    """
    return refresh_access_token(refresh_token=body.refresh_token, settings=settings)


@router.get("/metrics", include_in_schema=False)
def metrics(request: Request) -> Response:
    registry = getattr(request.app.state, "prometheus_registry", None)
    if registry is None:
        payload = ""
    else:
        payload = registry.render()
    return Response(
        content=payload,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
