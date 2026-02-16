from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path
from urllib import error, request
from urllib.parse import urlparse, urlunparse
import base64
import json
import os
import subprocess
import sys
import time


CORE_REQUIRED_SERVICES = (
    "postgres_timescaledb",
    "redis",
    "rabbitmq",
    "api",
    "notification_worker",
    "runtime_worker_market",
    "runtime_worker_orchestrator",
    "runtime_worker_simulation",
    "runtime_worker_oms",
    "runtime_worker_news",
)

FULL_PROFILE_SERVICES = (
    "real_execution_go",
    "prometheus",
    "alertmanager",
    "loki",
    "tempo",
    "grafana",
)

SMOKE_REAL_PROBE_QUEUE = "smoke.oms.events.order_updates"
SMOKE_REAL_PROBE_ROUTING_KEY = "oms.order.*"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    compose_up_cmd = ["docker", "compose"]
    if args.with_full_profile:
        compose_up_cmd.extend(["--profile", "full"])
    compose_up_cmd.extend(["up", "-d"])

    _run(["make", "env-validate"], cwd=repo_root)
    _run(compose_up_cmd, cwd=repo_root)
    time.sleep(args.wait_seconds)
    required_services = CORE_REQUIRED_SERVICES + FULL_PROFILE_SERVICES if args.with_full_profile else CORE_REQUIRED_SERVICES
    _assert_services_running(
        repo_root,
        required_services=required_services,
        timeout_seconds=args.service_wait_timeout,
        stability_seconds=args.service_stability_seconds,
    )
    _assert_runtime_bridge_ready()
    _run(
        ["uv", "run", "python", "-m", "services.notification_service.worker", "--validate-only"],
        cwd=repo_root,
        env_overrides={
            "TELEGRAM_BOT_TOKEN": "bot",
            "TELEGRAM_DEFAULT_CHAT_ID": "chat",
            "NOTIFY_CONSUMER_BACKEND": "inmemory",
            "RUNTIME_REQUIRE_DATABASE": "false",
        },
    )
    _run(
        ["uv", "run", "python", "-m", "services.notification_service.worker", "--once"],
        cwd=repo_root,
        env_overrides={
            "TELEGRAM_BOT_TOKEN": "bot",
            "TELEGRAM_DEFAULT_CHAT_ID": "chat",
            "NOTIFY_CONSUMER_BACKEND": "inmemory",
            "RUNTIME_REQUIRE_DATABASE": "false",
        },
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
    if args.with_full_profile:
        _assert_real_execution_rabbitmq_bridge_flow()

    if args.with_migrations:
        _run(["make", "migrate-up"], cwd=repo_root)

    print("Smoke test passed")
    return 0


def _assert_services_running(
    repo_root: Path,
    *,
    required_services: tuple[str, ...],
    timeout_seconds: float,
    stability_seconds: float,
) -> None:
    deadline = time.time() + max(1.0, timeout_seconds)
    required_stability = max(0.0, stability_seconds)
    stable_since: float | None = None
    missing: list[str] = []
    while time.time() < deadline:
        running = _list_running_services(repo_root)
        missing = sorted(set(required_services) - running)
        if not missing:
            if stable_since is None:
                stable_since = time.time()
            elif time.time() - stable_since >= required_stability:
                return
        else:
            stable_since = None
        time.sleep(1.0)
    raise RuntimeError(
        "docker compose up -d did not start all required services. Missing: "
        + ", ".join(missing)
    )


def _list_running_services(repo_root: Path) -> set[str]:
    proc = subprocess.run(
        ["docker", "compose", "ps", "--services", "--filter", "status=running"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        raise RuntimeError(f"failed to list docker compose services: {stderr}")
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def _assert_runtime_bridge_ready() -> None:
    response = request.urlopen("http://127.0.0.1:8000/health/liveness", timeout=5)
    payload = response.read().decode("utf-8")
    if '"status":"ok"' not in payload and '"status": "ok"' not in payload:
        raise RuntimeError("API liveness probe did not return status=ok")

    bridge_payload = {
        "command_id": "smoke-cmd",
        "operation": "CREATE_ORDER",
        "action": "BUY",
        "symbol": "BTC/USDT",
        "quantity": 0.01,
        "reduce_only": False,
        "idempotency_key": "smoke-idem",
        "client_order_id": "smoke-client",
        "exchange_order_id": "",
        "trace_id": "smoke-trace",
        "decision_id": "smoke-decision",
    }
    encoded = json.dumps(bridge_payload).encode("utf-8")
    req = request.Request(
        "http://127.0.0.1:8000/internal/execution/dispatch",
        data=encoded,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    bridge_response = request.urlopen(req, timeout=5)
    bridge_raw = bridge_response.read().decode("utf-8")
    if '"status":"submitted"' not in bridge_raw and '"status": "submitted"' not in bridge_raw:
        raise RuntimeError("Execution bridge endpoint did not return submitted status")


def _assert_real_execution_rabbitmq_bridge_flow() -> None:
    rabbitmq_api = _resolve_rabbitmq_http_api_for_host(
        os.getenv(
            "RUNTIME_RABBITMQ_HTTP_API_URL",
            os.getenv("NOTIFY_RABBITMQ_HTTP_API_URL", "http://127.0.0.1:15672/api"),
        )
    )
    rabbitmq_user = os.getenv("RABBITMQ_DEFAULT_USER", "guest")
    rabbitmq_pass = os.getenv("RABBITMQ_DEFAULT_PASS", "guest")
    _bootstrap_smoke_topology(
        api_base=rabbitmq_api,
        username=rabbitmq_user,
        password=rabbitmq_pass,
    )
    deadline = time.time() + 40.0
    publish_attempt = 0
    next_publish_at = 0.0
    while time.time() < deadline:
        now = time.time()
        if now >= next_publish_at:
            publish_attempt += 1
            publish_payload = {
                "trace_id": "smoke-real-trace",
                "decision_id": f"smoke-real-decision-{publish_attempt}",
                "mode": "REAL",
                "idempotency_key": f"smoke-real-idem-{publish_attempt}",
                "event_type": "execution.intent.created",
                "emitted_at": "2026-02-15T00:00:00Z",
                "payload": {
                    "strategy_id": "smoke",
                    "symbol": "BTC/USDT",
                    "action": "BUY",
                    "quantity": 0.02,
                    "client_order_id": f"smoke-real-client-{publish_attempt}",
                },
                "service": "smoke",
            }
            try:
                _rabbitmq_api_call(
                    api_base=rabbitmq_api,
                    username=rabbitmq_user,
                    password=rabbitmq_pass,
                    path="/exchanges/%2F/execution.events/publish",
                    payload={
                        "properties": {},
                        "routing_key": "execution.intent.real",
                        "payload": json.dumps(publish_payload),
                        "payload_encoding": "string",
                    },
                )
            except error.HTTPError as exc:
                if exc.code not in {400, 404}:
                    raise
                time.sleep(0.25)
                next_publish_at = now + 1.0
                continue
            next_publish_at = now + 1.0
        rows = _rabbitmq_api_call(
            api_base=rabbitmq_api,
            username=rabbitmq_user,
            password=rabbitmq_pass,
            path=f"/queues/%2F/{SMOKE_REAL_PROBE_QUEUE}/get",
            payload={
                "count": 5,
                "ackmode": "ack_requeue_false",
                "encoding": "auto",
                "truncate": 50000,
            },
        )
        for row in rows:
            payload = row.get("payload")
            parsed = json.loads(payload) if isinstance(payload, str) else payload
            if isinstance(parsed, dict) and str(parsed.get("event_type", "")).startswith("oms.order."):
                return
        time.sleep(0.25)
    raise RuntimeError("Did not observe OMS lifecycle event from real execution bridge flow")


def _resolve_rabbitmq_http_api_for_host(api_base_url: str) -> str:
    parsed = urlparse(api_base_url.strip())
    host = (parsed.hostname or "").strip().lower()
    if host != "rabbitmq":
        return api_base_url
    path = parsed.path or "/api"
    return urlunparse((parsed.scheme or "http", "127.0.0.1:15672", path, "", "", ""))


def _bootstrap_smoke_topology(*, api_base: str, username: str, password: str) -> None:
    _safe_rabbitmq_api_call(
        api_base=api_base,
        username=username,
        password=password,
        path="/exchanges/%2F/execution.events",
        payload={"type": "topic", "durable": True, "auto_delete": False, "internal": False, "arguments": {}},
        method="PUT",
    )
    _safe_rabbitmq_api_call(
        api_base=api_base,
        username=username,
        password=password,
        path="/exchanges/%2F/oms.events",
        payload={"type": "topic", "durable": True, "auto_delete": False, "internal": False, "arguments": {}},
        method="PUT",
    )
    _safe_rabbitmq_api_call(
        api_base=api_base,
        username=username,
        password=password,
        path="/queues/%2F/execution.intent.real",
        payload={"durable": True, "auto_delete": False, "arguments": {}},
        method="PUT",
    )
    _safe_rabbitmq_api_call(
        api_base=api_base,
        username=username,
        password=password,
        path="/queues/%2F/oms.events.order_updates",
        payload={"durable": True, "auto_delete": False, "arguments": {}},
        method="PUT",
    )
    _safe_rabbitmq_api_call(
        api_base=api_base,
        username=username,
        password=password,
        path=f"/queues/%2F/{SMOKE_REAL_PROBE_QUEUE}",
        payload={"durable": True, "auto_delete": False, "arguments": {}},
        method="PUT",
    )
    _safe_rabbitmq_api_call(
        api_base=api_base,
        username=username,
        password=password,
        path="/bindings/%2F/e/execution.events/q/execution.intent.real",
        payload={"routing_key": "execution.intent.real", "arguments": {}},
        method="POST",
    )
    _safe_rabbitmq_api_call(
        api_base=api_base,
        username=username,
        password=password,
        path="/bindings/%2F/e/oms.events/q/oms.events.order_updates",
        payload={"routing_key": "oms.order.*", "arguments": {}},
        method="POST",
    )
    _safe_rabbitmq_api_call(
        api_base=api_base,
        username=username,
        password=password,
        path=f"/bindings/%2F/e/oms.events/q/{SMOKE_REAL_PROBE_QUEUE}",
        payload={"routing_key": SMOKE_REAL_PROBE_ROUTING_KEY, "arguments": {}},
        method="POST",
    )


def _safe_rabbitmq_api_call(
    *,
    api_base: str,
    username: str,
    password: str,
    path: str,
    payload: dict[str, object],
    method: str,
) -> list[dict[str, object]]:
    try:
        return _rabbitmq_api_call(
            api_base=api_base,
            username=username,
            password=password,
            path=path,
            payload=payload,
            method=method,
        )
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8") if exc.fp is not None else ""
        if exc.code == 400 and "inequivalent arg" in body:
            return []
        raise


def _rabbitmq_api_call(
    *,
    api_base: str,
    username: str,
    password: str,
    path: str,
    payload: dict[str, object],
    method: str = "POST",
) -> list[dict[str, object]]:
    endpoint = api_base.rstrip("/") + path
    req = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        method=method,
        headers={"Content-Type": "application/json"},
    )
    credentials = f"{username}:{password}".encode("utf-8")
    req.add_header("Authorization", "Basic " + base64.b64encode(credentials).decode("ascii"))
    response = request.urlopen(req, timeout=5)
    decoded = response.read().decode("utf-8").strip()
    if not decoded:
        return []
    parsed = json.loads(decoded)
    if isinstance(parsed, list):
        return [dict(item) for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        return [parsed]
    return []


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
    parser.add_argument(
        "--service-wait-timeout",
        type=float,
        default=45.0,
        help="max time to wait for all required services to reach running state",
    )
    parser.add_argument(
        "--service-stability-seconds",
        type=float,
        default=3.0,
        help="minimum continuous running time required for required services",
    )
    parser.add_argument(
        "--with-full-profile",
        action="store_true",
        help="include optional full-profile services (observability + real_execution_go)",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
