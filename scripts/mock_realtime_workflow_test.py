from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path
from urllib import error, request
from urllib.parse import urlparse
import base64
import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

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
    "execution_intent": ("smoke.audit.execution_intent", "execution.events", "execution.intent.#"),
    "oms_updates": ("smoke.audit.oms_order_updates", "oms.events", "oms.order.*"),
    "strategy_lifecycle": ("smoke.audit.strategy_lifecycle", "strategy.events", "strategy.decision.#"),
    "notify": ("smoke.audit.notify", "notify.events", "notify.#"),
}

RUNTIME_QUEUES_TO_PURGE = (
    "market.canonical",
    "strategy.events.lifecycle",
    "execution.intent.mock",
    "execution.intent.real",
    "oms.events.order_updates",
    "notify.events.raw",
    "smoke.audit.execution_intent",
    "smoke.audit.oms_order_updates",
    "smoke.audit.strategy_lifecycle",
    "smoke.audit.notify",
)


def main(argv: list[str] | None = None) -> int:
    from services.shared.runtime.env_loader import load_dotenv_file

    load_dotenv_file()
    args = _parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]

    _run(["make", "env-validate"], cwd=repo_root)
    _run(["docker", "compose", "up", "-d"], cwd=repo_root)
    _assert_services_running(repo_root=repo_root, timeout_seconds=args.service_wait_timeout)
    _run(["docker", "compose", "stop", "runtime_worker_market"], cwd=repo_root)
    market_worker_stopped = True
    try:
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
        _purge_runtime_queues(
            api_base=rabbitmq_api,
            username=rabbitmq_user,
            password=rabbitmq_pass,
        )

        llm_content = _probe_litellm_or_mock(require_litellm=args.require_litellm)
        news_context = _fetch_real_news_context(require_real_news=args.require_real_news)
        selected_exchanges = _parse_exchange_list(args.market_exchanges)
        published_decisions: set[str] = set()
        market_fetch_results: list[dict[str, object]] = []
        for exchange in selected_exchanges:
            result = _publish_market_event(
                api_base=rabbitmq_api,
                username=rabbitmq_user,
                password=rabbitmq_pass,
                exchange=exchange,
                symbol="BTC/USDT",
                decision_suffix=exchange,
                news_context=news_context,
                require_real_market=args.require_real_market,
            )
            published_decisions.add(str(result["decision_id"]))
            market_fetch_results.append(result)
        _publish_notification_probe_event(
            api_base=rabbitmq_api,
            username=rabbitmq_user,
            password=rabbitmq_pass,
            llm_content=llm_content,
        )
        for result in market_fetch_results:
            print(
                "market_fetch"
                f" exchange={result['exchange']}"
                f" source={result['market_data_source']}"
                f" best_bid={result['best_bid']}"
                f" best_ask={result['best_ask']}"
                f" error={result['fetch_error']}"
            )

        _await_queue_message(
            api_base=rabbitmq_api,
            username=rabbitmq_user,
            password=rabbitmq_pass,
            queue_name=AUDIT_QUEUES["strategy_lifecycle"][0],
            timeout_seconds=args.workflow_timeout_seconds,
            required_event_prefix="agent.decision.",
            decision_ids=published_decisions,
        )
        _await_queue_message(
            api_base=rabbitmq_api,
            username=rabbitmq_user,
            password=rabbitmq_pass,
            queue_name=AUDIT_QUEUES["execution_intent"][0],
            timeout_seconds=args.workflow_timeout_seconds,
            required_event_prefix="execution.intent.",
            decision_ids=published_decisions,
        )
        _await_queue_message(
            api_base=rabbitmq_api,
            username=rabbitmq_user,
            password=rabbitmq_pass,
            queue_name=AUDIT_QUEUES["oms_updates"][0],
            timeout_seconds=args.workflow_timeout_seconds,
            required_event_prefix="oms.order.",
            decision_ids=published_decisions,
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
    finally:
        if market_worker_stopped:
            try:
                _run(["docker", "compose", "start", "runtime_worker_market"], cwd=repo_root)
            except RuntimeError as exc:
                print(f"Warning: failed to restart runtime_worker_market after mock workflow test: {exc}")


def _publish_market_event(
    *,
    api_base: str,
    username: str,
    password: str,
    exchange: str,
    symbol: str,
    decision_suffix: str,
    news_context: dict[str, object],
    require_real_market: bool,
) -> dict[str, object]:
    order_book = _fetch_live_order_book(
        exchange=exchange,
        symbol=symbol,
        limit=20,
        require_real_market=require_real_market,
    )
    bids = order_book["bids"]
    asks = order_book["asks"]
    if not bids or not asks:
        raise RuntimeError(f"{exchange} orderbook fetch returned empty levels for {symbol}")

    decision_id = str(uuid.uuid4())
    event = {
        "trace_id": str(uuid.uuid4()),
        "decision_id": decision_id,
        "mode": "MOCK",
        "idempotency_key": f"mock.market.{decision_suffix}:{uuid.uuid4()}",
        "event_type": "market.canonical.orderbook_delta",
        "emitted_at": _utc_now_iso(),
        "payload": {
            "exchange": exchange,
            "symbol": symbol,
            "timestamp_ms": order_book["timestamp_ms"],
            "bids": bids,
            "asks": asks,
            "news": news_context,
            "source": "exchange.rest",
            "market_data_source": order_book["data_source"],
            "market_fetch_error": order_book["fetch_error"],
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
    return {
        "decision_id": decision_id,
        "exchange": exchange,
        "market_data_source": order_book["data_source"],
        "fetch_error": order_book["fetch_error"],
        "best_bid": bids[0]["price"] if bids else None,
        "best_ask": asks[0]["price"] if asks else None,
    }


def _publish_notification_probe_event(
    *,
    api_base: str,
    username: str,
    password: str,
    llm_content: str,
) -> None:
    event = {
        "trace_id": str(uuid.uuid4()),
        "decision_id": str(uuid.uuid4()),
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


def _fetch_live_order_book(
    *,
    exchange: str,
    symbol: str,
    limit: int,
    require_real_market: bool,
) -> dict[str, object]:
    from services.market_ingestion.binance_http_adapter import BinanceHTTPOrderBookClient
    from services.market_ingestion.bitget_http_adapter import BitgetHTTPOrderBookClient

    timeout_seconds = max(1.0, float(os.getenv("MARKET_DATA_HTTP_TIMEOUT_SECONDS", "10.0")))
    normalized_exchange = exchange.strip().lower()
    if normalized_exchange == "binance":
        client = BinanceHTTPOrderBookClient(
            base_url=os.getenv("BINANCE_BASE_URL", "https://api.binance.com"),
            timeout_seconds=timeout_seconds,
        )
    elif normalized_exchange == "bitget":
        client = BitgetHTTPOrderBookClient(
            base_url=os.getenv("BITGET_BASE_URL", "https://api.bitget.com"),
            timeout_seconds=timeout_seconds,
        )
    else:
        raise RuntimeError(f"unsupported exchange for live fetch: {exchange}")

    try:
        raw = asyncio.run(client.fetch_order_book(symbol, limit=limit))
        bids = _levels_to_payload(raw.get("bids"))
        asks = _levels_to_payload(raw.get("asks"))
        if not bids or not asks:
            raise RuntimeError(f"{exchange} returned empty bids/asks for {symbol}")

        timestamp_ms = _to_int(raw.get("timestamp")) or int(time.time() * 1000)
        return {
            "timestamp_ms": timestamp_ms,
            "bids": bids,
            "asks": asks,
            "data_source": "live_rest",
            "fetch_error": None,
        }
    except Exception as exc:
        if require_real_market:
            raise
        now_ms = int(time.time() * 1000)
        base_price = 42000.0 if exchange == "binance" else 41990.0
        return {
            "timestamp_ms": now_ms,
            "bids": [
                {"price": base_price - 0.5, "amount": 9.0},
                {"price": base_price - 1.0, "amount": 4.0},
            ],
            "asks": [
                {"price": base_price + 0.5, "amount": 1.0},
                {"price": base_price + 1.0, "amount": 0.8},
            ],
            "data_source": "fallback_synthetic",
            "fetch_error": f"{exc.__class__.__name__}: {exc}",
        }


def _fetch_real_news_context(*, require_real_news: bool) -> dict[str, object]:
    news_items = _fetch_real_news_items(limit=4)
    if not news_items:
        if require_real_news:
            raise RuntimeError("failed to fetch real news items from configured feeds")
        return {
            "summary": "mock news fallback",
            "sentiment": 0.0,
            "source_count": 0,
            "items": [],
            "source": "mock",
        }

    summaries = [str(item.get("title", "")).strip() for item in news_items if str(item.get("title", "")).strip()]
    sentiment = 0.0
    lowered = " ".join(summaries).lower()
    if any(token in lowered for token in ("surge", "bull", "approval", "inflow", "rally")):
        sentiment += 0.2
    if any(token in lowered for token in ("selloff", "hack", "ban", "liquidation", "outflow")):
        sentiment -= 0.2
    summary = " | ".join(summaries[:2])

    return {
        "summary": summary or "real news sample",
        "sentiment": sentiment,
        "source_count": len({str(item.get('source', '')).strip() for item in news_items if item.get('source')}),
        "items": news_items,
        "source": "live_feeds",
    }


def _fetch_real_news_items(*, limit: int) -> list[dict[str, object]]:
    default_feeds = (
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://www.federalreserve.gov/feeds/press_all.xml",
    )
    raw_feed_list = os.getenv("MOCK_WORKFLOW_NEWS_FEEDS", ",".join(default_feeds))
    feed_urls = tuple(url.strip() for url in raw_feed_list.split(",") if url.strip())
    timeout_seconds = max(1.0, float(os.getenv("MOCK_WORKFLOW_NEWS_TIMEOUT_SECONDS", "8.0")))

    collected: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for feed_url in feed_urls:
        try:
            rss_xml = _http_get_text(feed_url, timeout_seconds=timeout_seconds)
            items = _parse_rss_items(feed_url=feed_url, rss_xml=rss_xml, limit=limit)
        except Exception:
            continue
        for item in items:
            source_item_id = str(item.get("source_item_id", "")).strip()
            if not source_item_id or source_item_id in seen_ids:
                continue
            seen_ids.add(source_item_id)
            collected.append(item)
            if len(collected) >= limit:
                return collected
    return collected


def _parse_rss_items(*, feed_url: str, rss_xml: str, limit: int) -> list[dict[str, object]]:
    root = ET.fromstring(rss_xml)
    items: list[dict[str, object]] = []
    source = _infer_source_name(feed_url)
    for item in root.findall(".//item"):
        title = _first_child_text(item, ("title",))
        link = _first_child_text(item, ("link",))
        published_at = _first_child_text(item, ("pubDate", "published")) or _utc_now_iso()
        description = _first_child_text(item, ("description", "summary"))
        if not title or not link:
            continue
        source_item_id = f"{source}:{link}"
        items.append(
            {
                "source": source,
                "source_item_id": source_item_id,
                "title": title,
                "url": link,
                "published_at": published_at,
                "content": description,
            }
        )
        if len(items) >= limit:
            break
    if len(items) < limit:
        for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
            title = _first_child_text(entry, ("{http://www.w3.org/2005/Atom}title",))
            updated = _first_child_text(entry, ("{http://www.w3.org/2005/Atom}updated",))
            content = _first_child_text(entry, ("{http://www.w3.org/2005/Atom}summary",))
            link = ""
            for link_node in entry.findall("{http://www.w3.org/2005/Atom}link"):
                href = str(link_node.attrib.get("href", "")).strip()
                if href:
                    link = href
                    break
            if not title or not link:
                continue
            source_item_id = f"{source}:{link}"
            items.append(
                {
                    "source": source,
                    "source_item_id": source_item_id,
                    "title": title,
                    "url": link,
                    "published_at": updated or _utc_now_iso(),
                    "content": content,
                }
            )
            if len(items) >= limit:
                break
    return items


def _first_child_text(element: ET.Element, tags: tuple[str, ...]) -> str:
    for tag in tags:
        child = element.find(tag)
        if child is not None and child.text is not None and child.text.strip():
            return child.text.strip()
    return ""


def _infer_source_name(feed_url: str) -> str:
    parsed = urlparse(feed_url)
    hostname = (parsed.hostname or "unknown").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname or "unknown"


def _levels_to_payload(raw_levels: object) -> list[dict[str, float]]:
    if not isinstance(raw_levels, list):
        return []
    normalized: list[dict[str, float]] = []
    for raw_level in raw_levels:
        if not isinstance(raw_level, (list, tuple)) or len(raw_level) < 2:
            continue
        try:
            price = float(raw_level[0])
            amount = float(raw_level[1])
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        normalized.append({"price": price, "amount": amount})
    return normalized


def _to_int(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _http_get_text(url: str, *, timeout_seconds: float) -> str:
    req = request.Request(url=url, method="GET")
    with request.urlopen(req, timeout=timeout_seconds) as response:  # noqa: S310 - explicit URL target
        return response.read().decode("utf-8", errors="ignore")


def _await_queue_message(
    *,
    api_base: str,
    username: str,
    password: str,
    queue_name: str,
    timeout_seconds: float,
    required_event_prefix: str,
    decision_ids: set[str] | None = None,
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
                if decision_ids is not None and str(parsed.get("decision_id", "")) not in decision_ids:
                    continue
                return parsed
        time.sleep(0.3)
    raise RuntimeError(f"Timeout waiting for event prefix {required_event_prefix} in queue {queue_name}")


def _purge_runtime_queues(
    *,
    api_base: str,
    username: str,
    password: str,
) -> None:
    for queue_name in RUNTIME_QUEUES_TO_PURGE:
        queue_ref = _encode_segment(queue_name)
        _rabbitmq_api_call(
            api_base=api_base,
            username=username,
            password=password,
            path=f"/queues/%2F/{queue_ref}/contents",
            payload={},
            method="DELETE",
        )


def _probe_litellm_or_mock(*, require_litellm: bool) -> str:
    from services.llm_gateway.litellm_http_adapter import LiteLLMHTTPError, LiteLLMHTTPProviderClient

    base_url = os.getenv("LITELLM_BASE_URL", "").strip()
    model = os.getenv("LITELLM_MODEL", "deepseek/deepseek-chat").strip() or "deepseek/deepseek-chat"
    expected_prefix = os.getenv("MOCK_WORKFLOW_LITELLM_EXPECTED_MODEL_PREFIX", "deepseek/").strip().lower()
    api_key = os.getenv("LITELLM_API_KEY", "").strip() or None
    timeout_seconds = float(os.getenv("LITELLM_TIMEOUT_SECONDS", "15.0"))

    if require_litellm and expected_prefix and not model.lower().startswith(expected_prefix):
        raise RuntimeError(
            f"LITELLM_MODEL must start with '{expected_prefix}' for this workflow. Current value: {model}"
        )

    if not base_url:
        if require_litellm:
            raise RuntimeError("LITELLM_BASE_URL is required when strict LiteLLM mode is enabled")
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
        if require_litellm:
            raise
        return f"mock_llm_decision: HOLD (litellm probe unavailable, model={model})"

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
        help="require LiteLLM probe success instead of fallback mocked LLM content",
    )
    parser.add_argument(
        "--require-real-news",
        action="store_true",
        help="require live news feed fetch success instead of fallback mocked news payload",
    )
    parser.add_argument(
        "--require-real-market",
        action="store_true",
        help="require live exchange orderbook fetch success instead of fallback mocked market payload",
    )
    parser.add_argument(
        "--market-exchanges",
        default="binance,bitget",
        help="comma-separated exchange ids to publish market events for (supported: binance,bitget)",
    )
    return parser.parse_args(argv)


def _parse_exchange_list(raw: str) -> tuple[str, ...]:
    supported = {"binance", "bitget"}
    parsed = tuple(item.strip().lower() for item in raw.split(",") if item.strip())
    if not parsed:
        raise RuntimeError("at least one exchange must be provided in --market-exchanges")
    invalid = sorted(set(parsed) - supported)
    if invalid:
        raise RuntimeError(f"unsupported exchanges in --market-exchanges: {', '.join(invalid)}")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
