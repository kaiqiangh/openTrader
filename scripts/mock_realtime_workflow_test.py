from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path
from urllib import error, request
import base64
import asyncio
import json
import os
import subprocess
import time
import uuid

from services.llm_gateway.litellm_http_adapter import LiteLLMHTTPError, LiteLLMHTTPProviderClient

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
)

AUDIT_QUEUES = {
    "execution_intent": ("smoke.audit.execution_intent", "execution.events", "execution.intent.mock"),
    "oms_updates": ("smoke.audit.oms_order_updates", "oms.events", "oms.order.*"),
    "strategy_lifecycle": ("smoke.audit.strategy_lifecycle", "strategy.events", "strategy.decision.#"),
    "notify": ("smoke.audit.notify", "notify.events", "notify.#"),
}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]

    _run(["make", "env-validate"], cwd=repo_root)
    _run(["docker", "compose", "up", "-d"], cwd=repo_root)
    _assert_services_running(repo_root=repo_root, timeout_seconds=args.service_wait_timeout)

    rabbitmq_api = _resolve_rabbitmq_http_api_for_host(
        os.getenv("RUNTIME_RABBITMQ_HTTP_API_URL", "http://127.0.0.1:15672/api")
    )
    rabbitmq_user = os.getenv("RABBITMQ_DEFAULT_USER", "guest")
    rabbitmq_pass = os.getenv("RABBITMQ_DEFAULT_PASS", "guest")
    _bootstrap_audit_topology(
        api_base=rabbitmq_api,
        username=rabbitmq_user,
        password=rabbitmq_pass,
    )

    llm_content = _probe_litellm_or_mock(require_litellm=args.require_litellm)
    _publish_market_event(
        api_base=rabbitmq_api,
        username=rabbitmq_user,
        password=rabbitmq_pass,
        exchange="binance",
        symbol="BTC/USDT",
        decision_suffix="binance",
    )
    _publish_market_event(
        api_base=rabbitmq_api,
        username=rabbitmq_user,
        password=rabbitmq_pass,
        exchange="bitget",
        symbol="BTC/USDT",
        decision_suffix="bitget",
    )
    _publish_notification_probe_event(
        api_base=rabbitmq_api,
        username=rabbitmq_user,
        password=rabbitmq_pass,
        llm_content=llm_content,
    )

    _await_queue_message(
        api_base=rabbitmq_api,
        username=rabbitmq_user,
        password=rabbitmq_pass,
        queue_name=AUDIT_QUEUES["strategy_lifecycle"][0],
        timeout_seconds=args.workflow_timeout_seconds,
        required_event_prefix="agent.decision.",
    )
    _await_queue_message(
        api_base=rabbitmq_api,
        username=rabbitmq_user,
        password=rabbitmq_pass,
        queue_name=AUDIT_QUEUES["execution_intent"][0],
        timeout_seconds=args.workflow_timeout_seconds,
        required_event_prefix="execution.intent.",
    )
    _await_queue_message(
        api_base=rabbitmq_api,
        username=rabbitmq_user,
        password=rabbitmq_pass,
        queue_name=AUDIT_QUEUES["oms_updates"][0],
        timeout_seconds=args.workflow_timeout_seconds,
        required_event_prefix="oms.order.",
    )
    _await_queue_message(
        api_base=rabbitmq_api,
        username=rabbitmq_user,
        password=rabbitmq_pass,
        queue_name=AUDIT_QUEUES["notify"][0],
        timeout_seconds=args.workflow_timeout_seconds,
        required_event_prefix="notify.",
    )

    _assert_db_count(repo_root=repo_root, query="SELECT COUNT(*) FROM orderbook_snapshots", minimum=1)
    _assert_db_count(repo_root=repo_root, query="SELECT COUNT(*) FROM runtime_oms_orders", minimum=1)
    _assert_db_count(repo_root=repo_root, query="SELECT COUNT(*) FROM runtime_oms_portfolio_snapshots", minimum=1)
    _assert_db_count(repo_root=repo_root, query="SELECT COUNT(*) FROM news_items", minimum=1)

    _assert_worker_log_contains(repo_root=repo_root, service="notification_worker", needle="notification.worker.envelope")
    print("Mock realtime workflow test passed")
    return 0


def _publish_market_event(
    *,
    api_base: str,
    username: str,
    password: str,
    exchange: str,
    symbol: str,
    decision_suffix: str,
) -> None:
    event = {
        "trace_id": f"mock-trace-{decision_suffix}-{uuid.uuid4()}",
        "decision_id": f"mock-decision-{decision_suffix}-{uuid.uuid4()}",
        "mode": "MOCK",
        "idempotency_key": f"mock.market.{decision_suffix}:{uuid.uuid4()}",
        "event_type": "market.canonical.orderbook_delta",
        "emitted_at": _utc_now_iso(),
        "payload": {
            "exchange": exchange,
            "symbol": symbol,
            "timestamp_ms": int(time.time() * 1000),
            "bids": [{"price": 42000.0, "amount": 3.0}, {"price": 41999.5, "amount": 2.0}],
            "asks": [{"price": 42001.0, "amount": 2.5}, {"price": 42001.5, "amount": 1.5}],
            "news": {
                "summary": "Macro risk stable; volatility contained",
                "sentiment": 0.1,
                "source_count": 2,
            },
        },
        "service": "mock_realtime_workflow_test",
    }
    _rabbitmq_api_call(
        api_base=api_base,
        username=username,
        password=password,
        path="/exchanges/%2F/market.events/publish",
        payload={
            "properties": {},
            "routing_key": "market.canonical",
            "payload": json.dumps(event),
            "payload_encoding": "string",
        },
    )


def _publish_notification_probe_event(
    *,
    api_base: str,
    username: str,
    password: str,
    llm_content: str,
) -> None:
    event = {
        "trace_id": f"notify-trace-{uuid.uuid4()}",
        "decision_id": f"notify-decision-{uuid.uuid4()}",
        "mode": "MOCK",
        "idempotency_key": f"notify.event:{uuid.uuid4()}",
        "event_type": "notify.system.critical_error",
        "emitted_at": _utc_now_iso(),
        "payload": {
            "severity": "CRITICAL",
            "strategy_id": "btc-momentum",
            "symbol": "BTC/USDT",
            "reason": "mock workflow notification probe",
            "llm_content_preview": llm_content[:200],
        },
        "service": "mock_realtime_workflow_test",
    }
    _rabbitmq_api_call(
        api_base=api_base,
        username=username,
        password=password,
        path="/exchanges/%2F/notify.events/publish",
        payload={
            "properties": {},
            "routing_key": "notify.system.critical_error",
            "payload": json.dumps(event),
            "payload_encoding": "string",
        },
    )


def _await_queue_message(
    *,
    api_base: str,
    username: str,
    password: str,
    queue_name: str,
    timeout_seconds: float,
    required_event_prefix: str,
) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    queue_ref = _encode_segment(queue_name)
    while time.time() < deadline:
        rows = _rabbitmq_api_call(
            api_base=api_base,
            username=username,
            password=password,
            path=f"/queues/%2F/{queue_ref}/get",
            payload={
                "count": 10,
                "ackmode": "ack_requeue_false",
                "encoding": "auto",
                "truncate": 50000,
            },
        )
        for row in rows:
            payload = row.get("payload")
            parsed = json.loads(payload) if isinstance(payload, str) else payload
            if not isinstance(parsed, dict):
                continue
            event_type = str(parsed.get("event_type", ""))
            if event_type.startswith(required_event_prefix):
                return parsed
        time.sleep(0.3)
    raise RuntimeError(f"Timeout waiting for event prefix {required_event_prefix} in queue {queue_name}")


def _probe_litellm_or_mock(*, require_litellm: bool) -> str:
    base_url = os.getenv("LITELLM_BASE_URL", "").strip()
    model = os.getenv("LITELLM_MODEL", "deepseek/deepseek-chat").strip() or "deepseek/deepseek-chat"
    api_key = os.getenv("LITELLM_API_KEY", "").strip() or None
    timeout_seconds = float(os.getenv("LITELLM_TIMEOUT_SECONDS", "15.0"))

    if not base_url:
        return "mock_llm_decision: BUY 0.1 BTC/USDT (litellm not configured)"

    client = LiteLLMHTTPProviderClient(
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )
    try:
        payload = asyncio.run(
            client.complete(
                model=model,
                messages=(
                    {"role": "system", "content": "You are a trading assistant."},
                    {"role": "user", "content": "Return one mock BTC/USDT action with quantity."},
                ),
                request_kwargs={"temperature": 0.1, "max_tokens": 64},
            )
        )
        content = ""
        if isinstance(payload, dict):
            choices = payload.get("choices")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                message = choices[0].get("message")
                if isinstance(message, dict):
                    content = str(message.get("content", "")).strip()
        if content:
            return content
    except (LiteLLMHTTPError, ValueError):
        pass

    if require_litellm:
        raise RuntimeError(f"LiteLLM probe failed for model '{model}'. Verify LITELLM_BASE_URL/LITELLM_API_KEY.")
    return f"mock_llm_decision: HOLD (litellm probe unavailable, model={model})"


def _assert_services_running(*, repo_root: Path, timeout_seconds: float) -> None:
    deadline = time.time() + max(1.0, timeout_seconds)
    missing: list[str] = []
    while time.time() < deadline:
        proc = subprocess.run(
            ["docker", "compose", "ps", "--services", "--filter", "status=running"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            time.sleep(0.5)
            continue
        running = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
        missing = sorted(set(REQUIRED_SERVICES) - running)
        if not missing:
            return
        time.sleep(1.0)
    raise RuntimeError(f"Missing required running services: {', '.join(missing)}")


def _assert_db_count(*, repo_root: Path, query: str, minimum: int) -> None:
    user = os.getenv("POSTGRES_USER", "open_trader")
    database = os.getenv("POSTGRES_DB", "open_trader")
    proc = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres_timescaledb",
            "psql",
            "-U",
            user,
            "-d",
            database,
            "-At",
            "-c",
            query,
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"DB query failed: {query} ({proc.stderr.strip()})")
    raw = proc.stdout.strip().splitlines()
    value = int(raw[-1]) if raw else 0
    if value < minimum:
        raise RuntimeError(f"DB validation failed for query '{query}': expected >= {minimum}, got {value}")


def _assert_worker_log_contains(*, repo_root: Path, service: str, needle: str) -> None:
    proc = subprocess.run(
        ["docker", "compose", "logs", "--tail=200", service],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to fetch logs for {service}: {proc.stderr.strip()}")
    if needle not in proc.stdout:
        raise RuntimeError(f"Expected log marker '{needle}' not found in {service} logs")


def _bootstrap_audit_topology(*, api_base: str, username: str, password: str) -> None:
    for queue_name, exchange_name, routing_key in AUDIT_QUEUES.values():
        queue_ref = _encode_segment(queue_name)
        exchange_ref = _encode_segment(exchange_name)
        _rabbitmq_api_call(
            api_base=api_base,
            username=username,
            password=password,
            path=f"/queues/%2F/{queue_ref}",
            payload={"durable": True, "auto_delete": False, "arguments": {}},
            method="PUT",
        )
        _rabbitmq_api_call(
            api_base=api_base,
            username=username,
            password=password,
            path=f"/bindings/%2F/e/{exchange_ref}/q/{queue_ref}",
            payload={"routing_key": routing_key, "arguments": {}},
            method="POST",
        )


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
    try:
        response = request.urlopen(req, timeout=5)  # noqa: S310
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8") if exc.fp is not None else ""
        if exc.code == 400 and "inequivalent arg" in body:
            return []
        raise RuntimeError(f"RabbitMQ HTTP call failed: {exc.code} {body}") from exc
    decoded = response.read().decode("utf-8").strip()
    if not decoded:
        return []
    parsed = json.loads(decoded)
    if isinstance(parsed, list):
        return [dict(item) for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        return [parsed]
    return []


def _run(cmd: list[str], *, cwd: Path) -> None:
    print("$ " + " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr.strip()}")


def _resolve_rabbitmq_http_api_for_host(api_base_url: str) -> str:
    raw = api_base_url.strip()
    if "rabbitmq:15672" not in raw:
        return raw
    return raw.replace("rabbitmq:15672", "127.0.0.1:15672")


def _encode_segment(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_args(argv: list[str] | None) -> Namespace:
    parser = ArgumentParser(description="Comprehensive mocked realtime workflow validation")
    parser.add_argument(
        "--service-wait-timeout",
        type=float,
        default=45.0,
        help="maximum seconds to wait for required services to run",
    )
    parser.add_argument(
        "--workflow-timeout-seconds",
        type=float,
        default=40.0,
        help="maximum seconds to wait for workflow events in audit queues",
    )
    parser.add_argument(
        "--require-litellm",
        action="store_true",
        help="fail when LiteLLM probe fails instead of falling back to mocked output",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
