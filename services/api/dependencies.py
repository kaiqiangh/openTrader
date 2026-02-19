from __future__ import annotations

from typing import Any

from fastapi import Request

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
    if repository is not None:
        settings = getattr(request.app.state, "settings", None)
        default_mode = getattr(settings, "default_mode", "MOCK")
        try:
            refreshed = repository.load_state(default_mode=default_mode)
        except Exception:
            refreshed = None
        if refreshed is not None:
            request.app.state.control_plane_state = refreshed
            state = refreshed
    if state is None:
        raise RuntimeError("control-plane state is not configured")
    return state


def get_control_plane_repository(request: Request) -> Any | None:
    return getattr(request.app.state, "control_plane_repository", None)
