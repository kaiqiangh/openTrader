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


REQUIRED_SERVICES = (
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
    "real_execution_go",
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
    _assert_runtime_bridge_ready()
    _run(
        ["uv", "run", "python", "-m", "services.notification_service.worker", "--validate-only"],
        cwd=repo_root,
        env_overrides={
            "TELEGRAM_BOT_TOKEN": "bot",
            "TELEGRAM_DEFAULT_CHAT_ID": "chat",
            "NOTIFY_CONSUMER_BACKEND": "inmemory",
        },
    )
    _run(
        ["uv", "run", "python", "-m", "services.notification_service.worker", "--once"],
        cwd=repo_root,
        env_overrides={
            "TELEGRAM_BOT_TOKEN": "bot",
            "TELEGRAM_DEFAULT_CHAT_ID": "chat",
            "NOTIFY_CONSUMER_BACKEND": "inmemory",
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
    _assert_real_execution_rabbitmq_bridge_flow()

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
    publish_payload = {
        "trace_id": "smoke-real-trace",
        "decision_id": "smoke-real-decision",
        "mode": "REAL",
        "idempotency_key": "smoke-real-idem",
        "event_type": "execution.intent.created",
        "emitted_at": "2026-02-15T00:00:00Z",
        "payload": {
            "strategy_id": "smoke",
            "symbol": "BTC/USDT",
            "action": "BUY",
            "quantity": 0.02,
            "client_order_id": "smoke-real-client",
        },
        "service": "smoke",
    }
    deadline = time.time() + 20.0
    published = False
    while time.time() < deadline:
        if not published:
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
                published = True
            except error.HTTPError as exc:
                if exc.code not in {400, 404}:
                    raise
                time.sleep(0.5)
                continue
        rows = _rabbitmq_api_call(
            api_base=rabbitmq_api,
            username=rabbitmq_user,
            password=rabbitmq_pass,
            path="/queues/%2F/oms.events.order_updates/get",
            payload={
                "count": 1,
                "ackmode": "ack_requeue_false",
                "encoding": "auto",
                "truncate": 50000,
            },
        )
        if rows:
            payload = rows[0].get("payload")
            if isinstance(payload, str):
                parsed = json.loads(payload)
            else:
                parsed = payload
            if isinstance(parsed, dict) and str(parsed.get("event_type", "")).startswith("oms.order."):
                return
        time.sleep(0.5)
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
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
