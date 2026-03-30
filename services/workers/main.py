"""Runtime worker CLI entry point.

Most logic has been split into focused modules:
- services.workers.settings   — configuration dataclasses
- services.workers.helpers    — shared utility functions
- services.workers.market     — MarketWorkerRunner
- services.workers.orchestrator — OrchestratorWorkerRunner
- services.workers.simulation — SimulationWorkerRunner
- services.workers.oms_lifecycle — OMSLifecycleWorkerRunner
- services.workers.news       — NewsWorkerRunner
- services.workers.builders   — build_runtime_worker, build_runtime_broker
"""

from __future__ import annotations

import asyncio
import time
from argparse import Namespace
from typing import Any

from services.shared.runtime.database import RuntimeDatabaseConfigError
from services.shared.runtime.structured_logging import StructuredLogger
from services.workers.builders import (
    build_runtime_broker,
    build_runtime_worker,
    _worker_idle_heartbeat_cycles,
)
from services.workers.helpers import (
    _correlation_from_activity,
    _worker_activity_snapshot,
)
from services.workers.settings import (
    RuntimeWorkerBuildResult,
    RuntimeWorkerSettings,
    RuntimeWorkerRunner,
    _resolve_runtime_engine,
    _validate_runtime_backend_policy,
    load_runtime_worker_settings,
)

# ── Backward-compatible re-exports for tests ─────────────────────────────────
# These symbols previously lived here; re-export so `from services.workers.main import ...`
# continues to work without modification.

# Also re-export helpers that tests import directly or patch via monkeypatch.setattr.
from services.workers.orchestrator import _build_llm_runtime  # noqa: F401
from services.workers.helpers import _resolve_requested_quantity  # noqa: F401
from services.workers.helpers import _http_get_text  # noqa: F401
from services.workers.helpers import _parse_rss_items  # noqa: F401

# Re-export so tests can monkeypatch runtime_main.create_runtime_engine_from_env
from services.shared.runtime.database import create_runtime_engine_from_env  # noqa: F401


_WORKER_SERVICE_NAME = "runtime_worker"


async def run_worker_loop(*, settings: RuntimeWorkerSettings, build: RuntimeWorkerBuildResult) -> int:
    logger = StructuredLogger(service=_WORKER_SERVICE_NAME)
    heartbeat_every = _worker_idle_heartbeat_cycles()

    if settings.bootstrap_topology and hasattr(build.broker, "bootstrap_topology"):
        await build.broker.bootstrap_topology()
        logger.info(
            event="runtime.worker.topology_bootstrapped",
            context={"worker": settings.worker, "broker_backend": settings.broker_backend},
        )

    if settings.validate_only:
        logger.info(
            event="runtime.worker.validation_passed",
            context={"worker": settings.worker, "broker_backend": settings.broker_backend},
        )
        return 0

    logger.info(
        event="runtime.worker.started",
        context={
            "worker": settings.worker,
            "broker_backend": settings.broker_backend,
            "mode": settings.mode,
            "once": settings.once,
            "poll_timeout_seconds": settings.poll_timeout_seconds,
            "idle_sleep_seconds": settings.idle_sleep_seconds,
            "max_idle_cycles": settings.max_idle_cycles,
            "heartbeat_every_idle_cycles": heartbeat_every,
        },
    )

    idle_cycles = 0
    total_cycles = 0
    work_cycles = 0
    while True:
        total_cycles += 1
        cycle_started = time.monotonic()
        try:
            did_work = await build.worker.run_once(timeout_seconds=settings.poll_timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - runtime loops must survive transient dependency failures
            cycle_latency_ms = max(0.0, (time.monotonic() - cycle_started) * 1000.0)
            activity = _worker_activity_snapshot(build.worker)
            context = {
                "worker": settings.worker,
                "cycle": total_cycles,
                "idle_cycles": idle_cycles,
                "latency_ms": cycle_latency_ms,
                "error": str(exc),
                "error_type": exc.__class__.__name__,
            }
            if activity:
                context["activity"] = activity
            logger.error(
                event="runtime.worker.cycle_failed",
                context=context,
                **_correlation_from_activity(activity),
            )
            if settings.once:
                logger.info(
                    event="runtime.worker.exited",
                    context={"worker": settings.worker, "reason": "once_cycle_failed", "cycle": total_cycles},
                )
                return 1
            idle_cycles += 1
            if settings.max_idle_cycles > 0 and idle_cycles >= settings.max_idle_cycles:
                logger.info(
                    event="runtime.worker.exited",
                    context={
                        "worker": settings.worker,
                        "reason": "max_idle_cycles_after_failure",
                        "cycle": total_cycles,
                        "idle_cycles": idle_cycles,
                    },
                )
                return 0
            await asyncio.sleep(settings.idle_sleep_seconds)
            continue

        cycle_latency_ms = max(0.0, (time.monotonic() - cycle_started) * 1000.0)
        activity = _worker_activity_snapshot(build.worker)
        if did_work:
            work_cycles += 1
            context = {
                "worker": settings.worker,
                "cycle": total_cycles,
                "work_cycles": work_cycles,
                "latency_ms": cycle_latency_ms,
            }
            if activity:
                context["activity"] = activity
            logger.info(
                event="runtime.worker.cycle_succeeded",
                context=context,
                **_correlation_from_activity(activity),
            )
            idle_cycles = 0
            if settings.once:
                logger.info(
                    event="runtime.worker.exited",
                    context={
                        "worker": settings.worker,
                        "reason": "once_cycle_completed",
                        "cycle": total_cycles,
                        "work_cycles": work_cycles,
                    },
                )
                return 0
            continue

        idle_cycles += 1
        if idle_cycles == 1 or (heartbeat_every > 0 and idle_cycles % heartbeat_every == 0):
            context = {
                "worker": settings.worker,
                "cycle": total_cycles,
                "idle_cycles": idle_cycles,
                "work_cycles": work_cycles,
                "latency_ms": cycle_latency_ms,
            }
            if activity:
                context["activity"] = activity
            logger.info(
                event="runtime.worker.idle_heartbeat",
                context=context,
                **_correlation_from_activity(activity),
            )
        if settings.once:
            logger.info(
                event="runtime.worker.exited",
                context={
                    "worker": settings.worker,
                    "reason": "once_no_work",
                    "cycle": total_cycles,
                    "idle_cycles": idle_cycles,
                },
            )
            return 0
        if settings.max_idle_cycles > 0 and idle_cycles >= settings.max_idle_cycles:
            logger.info(
                event="runtime.worker.exited",
                context={
                    "worker": settings.worker,
                    "reason": "max_idle_cycles",
                    "cycle": total_cycles,
                    "idle_cycles": idle_cycles,
                    "work_cycles": work_cycles,
                },
            )
            return 0
        await asyncio.sleep(settings.idle_sleep_seconds)


def main(argv: list[str] | None = None) -> int:
    startup_logger = StructuredLogger(service=_WORKER_SERVICE_NAME)
    parsed_args = _parse_args_for_main(argv)
    try:
        settings = load_runtime_worker_settings(parsed_args)
        _validate_runtime_backend_policy(settings=settings)
        runtime_engine = _resolve_runtime_engine(settings=settings)
        build = build_runtime_worker(settings=settings, runtime_engine=runtime_engine)
        return asyncio.run(run_worker_loop(settings=settings, build=build))
    except (RuntimeDatabaseConfigError, ValueError) as exc:
        startup_logger.error(
            event="runtime.worker.startup.validation_failed",
            context={"error": str(exc)},
        )
        return 1


def _parse_args_for_main(argv: list[str] | None) -> Namespace:
    """Delegate to settings._parse_args; this thin wrapper avoids a circular import."""
    from services.workers.settings import _parse_args

    return _parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
