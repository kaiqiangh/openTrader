"""Runtime worker settings and configuration."""

from __future__ import annotations

import os
from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.engine import Engine

from services.shared.runtime import database as _database
from services.shared.runtime.env_loader import load_dotenv_file
from services.workers.helpers import _to_bool


_WORKER_CHOICES = ("market", "orchestrator", "simulation", "oms", "news", "execution_lifecycle")


class RuntimeWorkerRunner(Protocol):
    async def run_once(self, *, timeout_seconds: float) -> bool: ...


@dataclass(frozen=True, slots=True)
class RuntimeWorkerSettings:
    worker: str
    broker_backend: str
    topology_path: str
    mode: str
    symbol: str
    strategy_id: str
    once: bool
    validate_only: bool
    max_idle_cycles: int
    poll_timeout_seconds: float
    idle_sleep_seconds: float
    bootstrap_topology: bool
    portfolio_base_balance_usd: float
    require_database: bool = True


@dataclass(frozen=True, slots=True)
class RuntimeWorkerBuildResult:
    worker: RuntimeWorkerRunner
    broker: Any


def load_runtime_worker_settings(args: Namespace | None = None) -> RuntimeWorkerSettings:
    load_dotenv_file()
    parsed = args or _parse_args(None)
    default_backend = os.getenv("RUNTIME_BROKER_BACKEND", "rabbitmq_http")
    default_mode = os.getenv("EXECUTION_MODE_DEFAULT", "MOCK")
    return RuntimeWorkerSettings(
        worker=parsed.worker,
        broker_backend=(parsed.broker_backend or default_backend).strip().lower(),
        topology_path=parsed.topology_path,
        mode=(parsed.mode or default_mode).strip().upper(),
        symbol=(parsed.symbol or os.getenv("TRADE_SYMBOL", "BTC/USDT")).strip().upper(),
        strategy_id=(parsed.strategy_id or os.getenv("STRATEGY_ID", "default-strategy")).strip(),
        once=bool(parsed.once),
        validate_only=bool(parsed.validate_only),
        max_idle_cycles=max(0, int(parsed.max_idle_cycles)),
        poll_timeout_seconds=max(0.0, float(parsed.poll_timeout_seconds)),
        idle_sleep_seconds=max(0.0, float(parsed.idle_sleep_seconds)),
        bootstrap_topology=bool(parsed.bootstrap_topology),
        portfolio_base_balance_usd=max(
            0.0,
            float(
                os.getenv(
                    "OMS_PORTFOLIO_BASE_BALANCE_USD",
                    "100000.0",
                )
            ),
        ),
        require_database=_to_bool(os.getenv("RUNTIME_REQUIRE_DATABASE", "true")),
    )


def _validate_runtime_backend_policy(*, settings: RuntimeWorkerSettings) -> None:
    if settings.require_database and settings.broker_backend == "inmemory":
        raise ValueError(
            "inmemory broker backend is disabled when RUNTIME_REQUIRE_DATABASE=true; use rabbitmq_http backend"
        )


def _resolve_runtime_engine(*, settings: RuntimeWorkerSettings) -> Engine | None:
    if not settings.require_database:
        return None
    runtime_engine = _database.create_runtime_engine_from_env()
    with runtime_engine.connect() as connection:
        value = connection.exec_driver_sql("SELECT 1").scalar_one()
        if value != 1:
            raise _database.RuntimeDatabaseConfigError("runtime database connectivity check returned an unexpected response")
    return runtime_engine


def _parse_args(argv: list[str] | None) -> Namespace:
    parser = ArgumentParser(description="Runtime worker entrypoints for phase-10 integration")
    parser.add_argument(
        "--worker",
        choices=_WORKER_CHOICES,
        required=True,
        help="worker role to run",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="process at most one work cycle and exit",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="build runtime dependencies and exit",
    )
    parser.add_argument(
        "--bootstrap-topology",
        action="store_true",
        help="bootstrap RabbitMQ topology before running the loop",
    )
    parser.add_argument(
        "--max-idle-cycles",
        type=int,
        default=0,
        help="exit after N empty polls (0 = unlimited)",
    )
    parser.add_argument(
        "--poll-timeout-seconds",
        type=float,
        default=float(os.getenv("RUNTIME_WORKER_POLL_TIMEOUT_SECONDS", "0.5")),
        help="queue poll timeout for consumer workers",
    )
    parser.add_argument(
        "--idle-sleep-seconds",
        type=float,
        default=float(os.getenv("RUNTIME_WORKER_IDLE_SLEEP_SECONDS", "0.5")),
        help="sleep duration between empty polls",
    )
    parser.add_argument(
        "--broker-backend",
        default=os.getenv("RUNTIME_BROKER_BACKEND"),
        help="runtime broker backend (inmemory or rabbitmq_http)",
    )
    parser.add_argument(
        "--topology-path",
        default="config/rabbitmq/topology.json",
        help="RabbitMQ topology path for inmemory and bootstrap flows",
    )
    parser.add_argument(
        "--mode",
        default=os.getenv("EXECUTION_MODE_DEFAULT"),
        help="runtime mode (MOCK or REAL)",
    )
    parser.add_argument(
        "--symbol",
        default=os.getenv("TRADE_SYMBOL", "BTC/USDT"),
        help="strategy/trading symbol",
    )
    parser.add_argument(
        "--strategy-id",
        default=os.getenv("STRATEGY_ID", "default-strategy"),
        help="strategy identifier",
    )
    return parser.parse_args(argv)
