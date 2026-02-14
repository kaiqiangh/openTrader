from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path
import os
import subprocess
import sys
import time


REQUIRED_SERVICES = (
    "postgres_timescaledb",
    "redis",
    "rabbitmq",
    "notification_worker",
    "prometheus",
    "alertmanager",
    "loki",
    "tempo",
    "grafana",
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    _run(["make", "env-validate"], cwd=repo_root)
    _run(["docker", "compose", "up", "-d"], cwd=repo_root)
    time.sleep(args.wait_seconds)
    _assert_services_running(repo_root)
    _run(
        ["uv", "run", "python", "-m", "services.notification_service.worker", "--validate-only"],
        cwd=repo_root,
    )
    _run(
        ["uv", "run", "python", "-m", "services.notification_service.worker", "--once"],
        cwd=repo_root,
        env_overrides={"NOTIFY_CONSUMER_BACKEND": "inmemory"},
    )
    api_probe = _run(
        [
            "uv",
            "run",
            "python",
            "-c",
            "from services.api.app import create_app; print('/metrics ready' if create_app() else 'failed')",
        ],
        cwd=repo_root,
    )
    if "/metrics ready" not in api_probe.stdout:
        raise RuntimeError("API smoke probe failed: '/metrics ready' not found in output")
    _run(["uv", "run", "python", "-m", "uvicorn", "--version"], cwd=repo_root)

    if args.with_migrations:
        _run(["make", "migrate-up"], cwd=repo_root)

    print("Smoke test passed")
    return 0


def _assert_services_running(repo_root: Path) -> None:
    proc = _run(
        ["docker", "compose", "ps", "--services", "--filter", "status=running"],
        cwd=repo_root,
    )
    running = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    missing = sorted(set(REQUIRED_SERVICES) - running)
    if missing:
        raise RuntimeError(
            "docker compose up -d did not start all required services. Missing: "
            + ", ".join(missing)
        )


def _run(
    cmd: list[str],
    *,
    cwd: Path,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    print("$ " + " ".join(cmd))
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.returncode != 0:
        if proc.stderr.strip():
            print(proc.stderr.strip(), file=sys.stderr)
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")
    return proc


def _parse_args(argv: list[str] | None) -> Namespace:
    parser = ArgumentParser(description="Run openTrader runtime smoke checks")
    parser.add_argument(
        "--with-migrations",
        action="store_true",
        help="include make migrate-up in smoke run",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=2.0,
        help="wait time after docker compose up before service checks",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
