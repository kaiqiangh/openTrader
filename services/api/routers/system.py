from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from services.api.auth import require_viewer
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
def health_readiness(state: ControlPlaneState = Depends(get_control_plane_state)) -> ReadinessResponse:
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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
