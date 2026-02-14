from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from services.api.routers import (
    control_router,
    dashboard_router,
    governance_router,
    ops_router,
    replay_router,
    system_router,
)
from services.api.settings import APISettings, load_api_settings
from services.api.state import ControlPlaneState, build_default_state


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield


def create_app(
    *,
    settings: APISettings | None = None,
    state: ControlPlaneState | None = None,
) -> FastAPI:
    resolved_settings = settings or load_api_settings()
    resolved_state = state or build_default_state(default_mode=resolved_settings.default_mode)

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        lifespan=_lifespan,
    )
    app.state.settings = resolved_settings
    app.state.control_plane_state = resolved_state

    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(system_router)
    app.include_router(control_router)
    app.include_router(ops_router)
    app.include_router(governance_router)
    app.include_router(replay_router)
    app.include_router(dashboard_router)
    return app
