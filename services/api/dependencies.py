from __future__ import annotations

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
    if state is None:
        raise RuntimeError("control-plane state is not configured")
    return state
