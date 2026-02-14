from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import AsyncIterator

from fastapi import FastAPI, Request
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
from services.shared.runtime.prometheus import PrometheusRegistry
from services.shared.runtime.structured_logging import StructuredLogger
from services.shared.runtime.trace_context import resolve_trace_context


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
    app.include_router(ops_router)
    app.include_router(governance_router)
    app.include_router(replay_router)
    app.include_router(dashboard_router)
    return app
