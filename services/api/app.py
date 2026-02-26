from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import Any, AsyncIterator, TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from services.api.routers import (
    control_router,
    dashboard_router,
    governance_router,
    internal_router,
    ops_router,
    replay_router,
    system_router,
)
from services.api.settings import APISettings, load_api_settings
from services.api.state import ControlPlaneState, build_default_state
from services.shared.runtime.prometheus import PrometheusRegistry
from services.shared.runtime.structured_logging import StructuredLogger
from services.shared.runtime.trace_context import resolve_trace_context

if TYPE_CHECKING:
    from services.api.repositories import ControlPlaneRepository


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield


def create_app(
    *,
    settings: APISettings | None = None,
    state: ControlPlaneState | None = None,
    repository: ControlPlaneRepository | None = None,
) -> FastAPI:
    resolved_settings = settings or load_api_settings()
    resolved_repository: Any | None = repository
    repository_load_error: Exception | None = None
    if resolved_repository is None and state is None:
        try:
            resolved_repository = _build_repository_from_env()
        except Exception as exc:
            repository_load_error = exc

    resolved_state = state
    if resolved_state is None and resolved_repository is not None:
        try:
            resolved_state = _load_state_from_repository(
                repository=resolved_repository,
                default_mode=resolved_settings.default_mode,
            )
        except Exception as exc:
            if resolved_settings.strict_database_mode:
                raise RuntimeError("failed to load control-plane state from repository") from exc
    if resolved_state is None:
        if resolved_settings.strict_database_mode and state is None:
            if repository_load_error is not None:
                raise RuntimeError("failed to initialize control-plane repository from runtime environment") from repository_load_error
            if resolved_repository is None:
                raise RuntimeError("control-plane repository is required when API_STRICT_DATABASE_MODE=true")
            raise RuntimeError("control-plane state is unavailable")
        resolved_state = build_default_state(default_mode=resolved_settings.default_mode)

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        lifespan=_lifespan,
    )
    if resolved_settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(resolved_settings.cors_allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=["traceparent", "x-trace-id"],
        )
    app.state.settings = resolved_settings
    app.state.control_plane_state = resolved_state
    app.state.control_plane_repository = resolved_repository
    app.state.prometheus_registry = PrometheusRegistry()
    app.state.structured_logger = StructuredLogger(service="api")

    @app.middleware("http")
    async def observability_middleware(request: Request, call_next):
        trace_context = resolve_trace_context(request.headers.get("traceparent"))
        request.state.trace_id = trace_context.trace_id
        request.state.traceparent = trace_context.traceparent

        logger: StructuredLogger = request.app.state.structured_logger
        metrics: PrometheusRegistry = request.app.state.prometheus_registry

        method = request.method.upper()
        path = request.url.path
        if (
            request.app.state.settings.read_only_mode
            and method in {"POST", "PUT", "PATCH", "DELETE"}
            and not path.startswith("/internal/")
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "API is running in read-only mode; write operations are disabled",
                },
            )
        logger.info(
            event="http.request.started",
            trace_id=trace_context.trace_id,
            mode=request.app.state.control_plane_state.mode,
            context={"method": method, "path": path},
        )

        started = perf_counter()
        status_code = 500
        error_type: str | None = None
        response = None
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            error_type = type(exc).__name__
            raise

        latency_seconds = max(0.0, perf_counter() - started)
        labels = {
            "service": "api",
            "method": method,
            "path": path,
            "status": str(status_code),
        }
        metrics.inc_counter(
            name="open_trader_http_requests_total",
            help_text="Total HTTP requests handled by service",
            label_values=labels,
        )
        metrics.observe_histogram(
            name="open_trader_http_request_duration_seconds",
            help_text="HTTP request processing latency seconds",
            value=latency_seconds,
            label_values={"service": "api", "method": method, "path": path},
        )
        log_method = logger.info if error_type is None else logger.error
        log_method(
            event="http.request.completed" if error_type is None else "http.request.failed",
            trace_id=trace_context.trace_id,
            mode=request.app.state.control_plane_state.mode,
            context={
                "method": method,
                "path": path,
                "status_code": status_code,
                "latency_ms": latency_seconds * 1000.0,
                "error_type": error_type,
            },
        )

        if response is None:
            raise RuntimeError("response missing after request middleware")

        response.headers["traceparent"] = trace_context.traceparent
        response.headers["x-trace-id"] = trace_context.trace_id
        return response

    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(system_router)
    app.include_router(control_router)
    app.include_router(internal_router)
    app.include_router(ops_router)
    app.include_router(governance_router)
    app.include_router(replay_router)
    app.include_router(dashboard_router)
    return app


def _build_repository_from_env() -> Any | None:
    from services.api.repositories import ControlPlaneRepository

    return ControlPlaneRepository.from_env()


def _load_state_from_repository(*, repository: Any, default_mode: str) -> ControlPlaneState | None:
    return repository.load_state(default_mode=default_mode)
