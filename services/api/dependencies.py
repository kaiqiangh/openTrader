from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status

from services.api.settings import APISettings
from services.api.state import ControlPlaneState


def get_api_settings(request: Request) -> APISettings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise RuntimeError("API settings are not configured")
    return settings


def get_control_plane_state(request: Request) -> ControlPlaneState:
    state = getattr(request.app.state, "control_plane_state", None)
    repository = getattr(request.app.state, "control_plane_repository", None)
    settings = getattr(request.app.state, "settings", None)
    strict_mode = bool(getattr(settings, "strict_database_mode", False))
    if repository is not None:
        default_mode = getattr(settings, "default_mode", "MOCK")
        try:
            refreshed = repository.load_state(default_mode=default_mode)
        except Exception as exc:
            if strict_mode:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Control-plane repository unavailable",
                ) from exc
            refreshed = None
        if refreshed is not None:
            request.app.state.control_plane_state = refreshed
            state = refreshed
    if state is None:
        if strict_mode:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Control-plane state unavailable",
            )
        raise RuntimeError("control-plane state is not configured")
    return state


def get_control_plane_repository(request: Request) -> Any | None:
    return getattr(request.app.state, "control_plane_repository", None)
