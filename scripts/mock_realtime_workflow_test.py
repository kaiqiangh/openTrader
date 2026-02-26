from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import asyncio
import json
import os
import random
import subprocess
import sys
import time
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.llm_gateway.contracts import GatewaySettings, LLMRequest, ProviderSettings  # noqa: E402
from services.llm_gateway.gateway import LLMGateway  # noqa: E402
from services.llm_gateway.litellm_http_adapter import LiteLLMHTTPProviderClient  # noqa: E402
from services.llm_gateway.sqlalchemy_stores import SQLAlchemyLLMCallStore  # noqa: E402
from services.shared.runtime.database import create_runtime_engine_from_env  # noqa: E402
from services.shared.runtime.env_loader import load_dotenv_file  # noqa: E402
from services.shared.runtime.rabbitmq_http_broker import RabbitMQHTTPTopicBroker  # noqa: E402

REQUIRED_CORE_SERVICES = (
    "postgres_timescaledb",
    "rabbitmq",
    "runtime_worker_market",
    "runtime_worker_orchestrator",
    "runtime_worker_simulation",
    "runtime_worker_oms",
    "runtime_worker_news",
)


@dataclass(frozen=True, slots=True)
class MarketSnapshotContext:
    exchange: str
    symbol: str
    snapshot_time: datetime
    bids: tuple[dict[str, float], ...]
    asks: tuple[dict[str, float], ...]
    best_bid: float
    best_ask: float
    spread_bps: float


@dataclass(frozen=True, slots=True)
class KlineContext:
    exchange: str
    symbol: str
    interval: str
    bar_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class NewsContext:
    summary_id: str
    summary_text: str
    sentiment: float
    source_news_ids: tuple[str, ...]


def main(argv: list[str] | None = None) -> int:
    load_dotenv_file()
    args = _parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]

    if args.seed is not None:
        random.seed(args.seed)

    if not args.skip_compose:
        _run(["make", "env-validate"], cwd=repo_root)
        _run(["docker", "compose", "up", "-d"], cwd=repo_root)
        _assert_services_running(repo_root=repo_root, timeout_seconds=args.service_wait_timeout)

    engine = _create_host_runtime_engine()
    started_at = datetime.now(UTC)
    strategy_id = os.getenv("STRATEGY_ID", "default-strategy")
    strategy_uuid = _coerce_uuid(strategy_id)

    exchanges = _parse_exchange_list(args.market_exchanges)
    orderbook_context = _fetch_latest_orderbook_context(
        engine=engine,
        symbol=args.symbol,
        exchanges=exchanges,
        lookback_minutes=args.lookback_minutes,
    )
    kline_context = _fetch_latest_kline_context(
        engine=engine,
        symbol=args.symbol,
        interval=args.interval,
        preferred_exchange=orderbook_context.exchange,
        lookback_minutes=args.lookback_minutes,
    )
    news_context = _fetch_latest_news_context(
        engine=engine,
        lookback_minutes=args.lookback_minutes,
    )

    trace_id, decision_id = _workflow_ids(seed=args.seed, symbol=args.symbol, interval=args.interval)
    llm_response = asyncio.run(
        _run_strict_llm_call(
            engine=engine,
            trace_id=trace_id,
            decision_id=decision_id,
            strategy_id=strategy_uuid,
            symbol=args.symbol,
            interval=args.interval,
            orderbook=orderbook_context,
            kline=kline_context,
            news=news_context,
            seed=args.seed,
        )
    )

    market_event = _build_market_event(
        trace_id=trace_id,
        decision_id=decision_id,
        symbol=args.symbol,
        orderbook=orderbook_context,
        kline=kline_context,
        news=news_context,
        llm_content=llm_response,
    )
    asyncio.run(_publish_market_event(envelope=market_event))

    expected_order_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sim-order:execution.intent:mock:{decision_id}"))
    _await_workflow_persistence(
        engine=engine,
        decision_id=decision_id,
        expected_order_id=expected_order_id,
        started_at=started_at,
        timeout_seconds=args.workflow_timeout_seconds,
        expect_news_links=bool(news_context.source_news_ids),
    )

    print(
        "workflow.ok"
        f" decision_id={decision_id}"
        f" trace_id={trace_id}"
        f" exchange={orderbook_context.exchange}"
        f" symbol={args.symbol}"
        f" interval={args.interval}"
        f" llm_preview={_single_line_preview(llm_response)}"
    )
    return 0


def _parse_args(argv: list[str] | None) -> Namespace:
    parser = ArgumentParser(description="Strict real-data mock-trade runtime workflow validation")
    parser.add_argument("--seed", type=int, default=None, help="optional deterministic seed")
    parser.add_argument("--symbol", default="BTC/USDT", help="market symbol (default: BTC/USDT)")
    parser.add_argument("--interval", default="1m", help="kline interval to use from DB context")
    parser.add_argument(
        "--lookback-minutes",
        type=int,
        default=15,
        help="required data freshness window for orderbook/kline/news",
    )
    parser.add_argument(
        "--market-exchanges",
        default="binance,bitget",
        help="comma-separated exchanges allowed for DB context selection",
    )
    parser.add_argument(
        "--service-wait-timeout",
        type=float,
        default=45.0,
        help="maximum seconds to wait for required services to run",
    )
    parser.add_argument(
        "--workflow-timeout-seconds",
        type=float,
        default=60.0,
        help="maximum seconds to wait for trace/execution persistence",
    )
    parser.add_argument(
        "--skip-compose",
        action="store_true",
        help="skip compose bring-up and service checks",
    )

    # Legacy compatibility flags retained as aliases/no-op compatibility.
    parser.add_argument("--require-litellm", action="store_true", help="deprecated (strict LLM is always enabled)")
    parser.add_argument("--require-real-news", action="store_true", help="deprecated (news is read from DB only)")
    parser.add_argument("--require-real-market", action="store_true", help="deprecated (market data is read from DB)")

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


def _workflow_ids(*, seed: int | None, symbol: str, interval: str) -> tuple[str, str]:
    if seed is None:
        return str(uuid.uuid4()), str(uuid.uuid4())
    scope = f"seed={seed}|symbol={symbol.upper()}|interval={interval.lower()}"
    trace_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"trace:{scope}"))
    decision_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"decision:{scope}"))
    return trace_id, decision_id


async def _run_strict_llm_call(
    *,
    engine: Engine,
    trace_id: str,
    decision_id: str,
    strategy_id: str,
    symbol: str,
    interval: str,
    orderbook: MarketSnapshotContext,
    kline: KlineContext,
    news: NewsContext,
    seed: int | None,
) -> str:
    base_url = os.getenv("LITELLM_BASE_URL", "").strip()
    if not base_url:
        raise RuntimeError("LITELLM_BASE_URL is required for strict workflow execution")

    configured_model = os.getenv("LITELLM_MODEL", "deepseek/deepseek-chat").strip() or "deepseek/deepseek-chat"
    model = _normalize_litellm_model(base_url=base_url, model=configured_model)
    timeout_seconds = max(1.0, float(os.getenv("LITELLM_TIMEOUT_SECONDS", "15.0")))
    api_key = os.getenv("LITELLM_API_KEY", "").strip() or None

    provider_alias = "litellm"
    settings = GatewaySettings(
        providers={
            provider_alias: ProviderSettings(
                alias=provider_alias,
                model=model,
                timeout_ms=int(timeout_seconds * 1000),
                max_retries=1,
                enabled=True,
            )
        },
        default_provider_order=(provider_alias,),
    )
    gateway = LLMGateway(
        settings=settings,
        provider_clients={
            provider_alias: LiteLLMHTTPProviderClient(
                base_url=base_url,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
            )
        },
        call_store=SQLAlchemyLLMCallStore(connection=engine, ensure_schema=False),
    )

    request = LLMRequest(
        trace_id=trace_id,
        decision_id=decision_id,
        strategy_id=strategy_id,
        agent_name="workflow_probe",
        messages=(
            {
                "role": "system",
                "content": (
                    "Return one concise BTC/USDT trading thought as JSON with keys "
                    "action, confidence, and rationale."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "symbol": symbol,
                        "interval": interval,
                        "seed": seed,
                        "orderbook": {
                            "exchange": orderbook.exchange,
                            "best_bid": orderbook.best_bid,
                            "best_ask": orderbook.best_ask,
                            "spread_bps": orderbook.spread_bps,
                        },
                        "kline": {
                            "exchange": kline.exchange,
                            "open": kline.open,
                            "high": kline.high,
                            "low": kline.low,
                            "close": kline.close,
                            "volume": kline.volume,
                        },
                        "news": {
                            "summary": news.summary_text,
                            "sentiment": news.sentiment,
                            "source_count": len(news.source_news_ids),
                        },
                    },
                    ensure_ascii=True,
                ),
            },
        ),
        temperature=0.1,
        max_tokens=180,
        metadata={"workflow": "mock_realtime_workflow_test", "strict": True},
    )

    response = await gateway.generate(request)
    content = response.content.strip()
    if not content:
        raise RuntimeError("LLM call succeeded but returned empty content")
    return content


def _normalize_litellm_model(*, base_url: str, model: str) -> str:
    normalized_model = model.strip()
    if not normalized_model:
        return "deepseek/deepseek-chat"
    parsed_host = urlparse(base_url).netloc.lower()
    host_scope = parsed_host or base_url.lower()
    # Direct DeepSeek endpoint expects "deepseek-chat"; LiteLLM proxy commonly uses "deepseek/deepseek-chat".
    if "api.deepseek.com" in host_scope and normalized_model.startswith("deepseek/"):
        suffix = normalized_model.split("/", 1)[1].strip()
        return suffix or "deepseek-chat"
    return normalized_model


def _build_market_event(
    *,
    trace_id: str,
    decision_id: str,
    symbol: str,
    orderbook: MarketSnapshotContext,
    kline: KlineContext,
    news: NewsContext,
    llm_content: str,
) -> dict[str, Any]:
    snapshot_time_ms = int(orderbook.snapshot_time.timestamp() * 1000)
    payload = {
        "exchange": orderbook.exchange,
        "symbol": symbol,
        "timestamp_ms": snapshot_time_ms,
        "bids": [dict(item) for item in orderbook.bids],
        "asks": [dict(item) for item in orderbook.asks],
        "kline": {
            "exchange": kline.exchange,
            "interval": kline.interval,
            "time": _isoformat(kline.bar_time),
            "open": kline.open,
            "high": kline.high,
            "low": kline.low,
            "close": kline.close,
            "volume": kline.volume,
        },
        "news": {
            "summary": news.summary_text,
            "sentiment": news.sentiment,
            "source_count": len(news.source_news_ids),
            "summary_id": news.summary_id,
            "news_ids": list(news.source_news_ids),
        },
        "llm_probe": {
            "content_preview": _single_line_preview(llm_content),
        },
    }
    return {
        "trace_id": trace_id,
        "decision_id": decision_id,
        "mode": "MOCK",
        "idempotency_key": f"workflow.market:{decision_id}",
        "event_type": "market.canonical.orderbook_delta",
        "emitted_at": _utc_now_iso(),
        "payload": payload,
        "service": "mock_realtime_workflow_test",
    }


async def _publish_market_event(*, envelope: Mapping[str, Any]) -> None:
    api_base = _resolve_rabbitmq_http_api_for_host(
        os.getenv("RUNTIME_RABBITMQ_HTTP_API_URL", "http://127.0.0.1:15672/api")
    )
    broker = RabbitMQHTTPTopicBroker(
        api_base_url=api_base,
        username=os.getenv("RABBITMQ_DEFAULT_USER", "guest"),
        password=os.getenv("RABBITMQ_DEFAULT_PASS", "guest"),
        topology_path="config/rabbitmq/topology.json",
        request_timeout_seconds=max(1.0, float(os.getenv("RUNTIME_BROKER_HTTP_TIMEOUT_SECONDS", "2.0"))),
    )
    await broker.bootstrap_topology()
    await broker.publish(routing_key="market.canonical", message=dict(envelope))


def _fetch_latest_orderbook_context(
    *,
    engine: Engine,
    symbol: str,
    exchanges: Sequence[str],
    lookback_minutes: int,
) -> MarketSnapshotContext:
    since = datetime.now(UTC) - timedelta(minutes=max(1, lookback_minutes))
    for exchange in exchanges:
        row = _fetch_one(
            engine=engine,
            query=text(
                """
                SELECT exchange, symbol, snapshot_time, bids, asks, best_bid, best_ask, spread_bps
                FROM orderbook_snapshots
                WHERE exchange = :exchange
                  AND symbol = :symbol
                  AND snapshot_time >= :since
                ORDER BY snapshot_time DESC
                LIMIT 1
                """
            ),
            params={"exchange": exchange, "symbol": symbol.upper(), "since": since},
        )
        if row is None:
            continue
        snapshot_time = _coerce_datetime(row.get("snapshot_time"))
        bids = _normalize_levels(row.get("bids"))
        asks = _normalize_levels(row.get("asks"))
        if not bids or not asks:
            continue
        return MarketSnapshotContext(
            exchange=str(row["exchange"]),
            symbol=str(row["symbol"]),
            snapshot_time=snapshot_time,
            bids=tuple(bids),
            asks=tuple(asks),
            best_bid=float(row.get("best_bid") or bids[0]["price"]),
            best_ask=float(row.get("best_ask") or asks[0]["price"]),
            spread_bps=float(row.get("spread_bps") or 0.0),
        )

    raise RuntimeError(
        "No fresh orderbook snapshot found in Postgres for requested exchanges/symbol. "
        "Run core runtime workers for at least a few minutes and retry."
    )


def _fetch_latest_kline_context(
    *,
    engine: Engine,
    symbol: str,
    interval: str,
    preferred_exchange: str,
    lookback_minutes: int,
) -> KlineContext:
    since = datetime.now(UTC) - timedelta(minutes=max(1, lookback_minutes))
    row = _fetch_one(
        engine=engine,
        query=text(
            """
            SELECT exchange, symbol, "interval", time, open, high, low, close, volume
            FROM klines
            WHERE exchange = :exchange
              AND symbol = :symbol
              AND "interval" = :interval
              AND time >= :since
            ORDER BY time DESC
            LIMIT 1
            """
        ),
        params={
            "exchange": preferred_exchange,
            "symbol": symbol.upper(),
            "interval": interval,
            "since": since,
        },
    )
    if row is None:
        row = _fetch_one(
            engine=engine,
            query=text(
                """
                SELECT exchange, symbol, "interval", time, open, high, low, close, volume
                FROM klines
                WHERE symbol = :symbol
                  AND "interval" = :interval
                  AND time >= :since
                ORDER BY time DESC
                LIMIT 1
                """
            ),
            params={"symbol": symbol.upper(), "interval": interval, "since": since},
        )
    if row is None:
        raise RuntimeError(
            "No fresh kline rows found in Postgres for requested symbol/interval. "
            "Wait for market worker kline polling and retry."
        )

    return KlineContext(
        exchange=str(row["exchange"]),
        symbol=str(row["symbol"]),
        interval=str(row["interval"]),
        bar_time=_coerce_datetime(row.get("time")),
        open=float(row.get("open") or 0.0),
        high=float(row.get("high") or 0.0),
        low=float(row.get("low") or 0.0),
        close=float(row.get("close") or 0.0),
        volume=float(row.get("volume") or 0.0),
    )


def _fetch_latest_news_context(*, engine: Engine, lookback_minutes: int) -> NewsContext:
    since = datetime.now(UTC) - timedelta(minutes=max(1, lookback_minutes))
    row = _fetch_one(
        engine=engine,
        query=text(
            """
            SELECT summary_id, summary_text, generated_at
            FROM news_summaries
            WHERE generated_at >= :since
            ORDER BY generated_at DESC
            LIMIT 1
            """
        ),
        params={"since": since},
    )
    if row is None:
        row = _fetch_one(
            engine=engine,
            query=text(
                """
                SELECT summary_id, summary_text, generated_at
                FROM news_summaries
                ORDER BY generated_at DESC
                LIMIT 1
                """
            ),
            params={},
        )
    if row is None:
        raise RuntimeError(
            "No news_summaries row found. Run runtime_worker_news and retry."
        )

    summary_id = str(row["summary_id"])
    source_news_ids = _fetch_summary_sources(engine=engine, summary_id=summary_id)
    sentiment = _news_sentiment(engine=engine, source_news_ids=source_news_ids)
    return NewsContext(
        summary_id=summary_id,
        summary_text=str(row.get("summary_text") or "news_unavailable"),
        sentiment=sentiment,
        source_news_ids=tuple(source_news_ids),
    )


def _fetch_summary_sources(*, engine: Engine, summary_id: str) -> list[str]:
    tables = ("news_summary_sources", "runtime_news_summary_sources")
    for table in tables:
        try:
            rows = _fetch_all(
                engine=engine,
                query=text(f"SELECT news_id FROM {table} WHERE summary_id = :summary_id ORDER BY news_id ASC"),
                params={"summary_id": summary_id},
            )
        except SQLAlchemyError:
            continue
        source_ids = [str(row["news_id"]) for row in rows if row.get("news_id") is not None]
        if source_ids:
            return source_ids
    return []


def _news_sentiment(*, engine: Engine, source_news_ids: Sequence[str]) -> float:
    if not source_news_ids:
        return 0.0
    sentiment_total = 0.0
    count = 0
    for news_id in source_news_ids:
        row = _fetch_one(
            engine=engine,
            query=text(
                """
                SELECT AVG(sentiment_score) AS avg_sentiment
                FROM news_tags
                WHERE news_id = :news_id
                """
            ),
            params={"news_id": news_id},
        )
        if row is None:
            continue
        value = row.get("avg_sentiment")
        if value is None:
            continue
        sentiment_total += float(value)
        count += 1
    if count == 0:
        return 0.0
    return sentiment_total / count


def _await_workflow_persistence(
    *,
    engine: Engine,
    decision_id: str,
    expected_order_id: str,
    started_at: datetime,
    timeout_seconds: float,
    expect_news_links: bool,
) -> None:
    deadline = time.time() + max(1.0, timeout_seconds)
    required_runs = 5
    required_messages = 10

    while time.time() < deadline:
        llm_calls = _scalar_int(
            engine=engine,
            query=text("SELECT COUNT(*) FROM llm_calls WHERE decision_id = :decision_id"),
            params={"decision_id": decision_id},
        )
        trace_count = _scalar_int(
            engine=engine,
            query=text("SELECT COUNT(*) FROM decision_traces WHERE decision_id = :decision_id"),
            params={"decision_id": decision_id},
        )
        run_count = _scalar_int(
            engine=engine,
            query=text("SELECT COUNT(*) FROM agent_runs WHERE decision_id = :decision_id"),
            params={"decision_id": decision_id},
        )
        message_count = _scalar_int(
            engine=engine,
            query=text(
                """
                SELECT COUNT(*)
                FROM agent_messages am
                JOIN agent_runs ar ON ar.agent_run_id = am.agent_run_id
                WHERE ar.decision_id = :decision_id
                """
            ),
            params={"decision_id": decision_id},
        )
        order_count = _scalar_int(
            engine=engine,
            query=text("SELECT COUNT(*) FROM orders WHERE id = :order_id"),
            params={"order_id": expected_order_id},
        )
        lifecycle_count = _scalar_int(
            engine=engine,
            query=text(
                """
                SELECT COUNT(*)
                FROM fills
                WHERE order_id = :order_id
                """
            ),
            params={"order_id": expected_order_id},
        )
        snapshot_count = _scalar_int(
            engine=engine,
            query=text(
                """
                SELECT COUNT(*)
                FROM portfolio_snapshots
                WHERE created_at >= :started_at
                """
            ),
            params={"started_at": _isoformat(started_at)},
        )
        news_link_count = _scalar_int(
            engine=engine,
            query=text("SELECT COUNT(*) FROM decision_news_links WHERE decision_id = :decision_id"),
            params={"decision_id": decision_id},
        )

        news_links_ok = news_link_count >= 1 if expect_news_links else True
        if (
            llm_calls >= 1
            and trace_count >= 1
            and run_count >= required_runs
            and message_count >= required_messages
            and order_count >= 1
            and lifecycle_count >= 1
            and snapshot_count >= 1
            and news_links_ok
        ):
            return

        time.sleep(0.5)

    raise RuntimeError(
        "Workflow persistence timeout. "
        f"decision_id={decision_id} "
        f"expected_order_id={expected_order_id}"
    )


def _fetch_one(*, engine: Engine, query: Any, params: Mapping[str, Any]) -> Mapping[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(query, dict(params)).mappings().first()
    if row is None:
        return None
    return dict(row)


def _fetch_all(*, engine: Engine, query: Any, params: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(query, dict(params)).mappings().all()
    return [dict(row) for row in rows]


def _scalar_int(*, engine: Engine, query: Any, params: Mapping[str, Any]) -> int:
    with engine.connect() as connection:
        value = connection.execute(query, dict(params)).scalar_one()
    return int(value)


def _normalize_levels(raw: Any) -> list[dict[str, float]]:
    parsed = _parse_json_if_needed(raw)
    if not isinstance(parsed, list):
        return []
    levels: list[dict[str, float]] = []
    for item in parsed:
        if isinstance(item, Mapping):
            price = _to_float(item.get("price"))
            amount = _to_float(item.get("amount"))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            price = _to_float(item[0])
            amount = _to_float(item[1])
        else:
            continue
        if price <= 0 or amount <= 0:
            continue
        levels.append({"price": price, "amount": amount})
    return levels


def _parse_json_if_needed(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    raise RuntimeError(f"unable to coerce datetime from value: {value!r}")


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _coerce_uuid(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(candidate))
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, candidate))


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
        missing = sorted(set(REQUIRED_CORE_SERVICES) - running)
        if not missing:
            return
        time.sleep(1.0)
    raise RuntimeError(f"Missing required running services: {', '.join(missing)}")


def _resolve_rabbitmq_http_api_for_host(api_base_url: str) -> str:
    raw = api_base_url.strip()
    if "rabbitmq:15672" not in raw:
        return raw
    return raw.replace("rabbitmq:15672", "127.0.0.1:15672")


def _single_line_preview(value: str, *, limit: int = 180) -> str:
    compact = " ".join(value.strip().split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _utc_now_iso() -> str:
    return _isoformat(datetime.now(UTC))


def _run(cmd: list[str], *, cwd: Path) -> None:
    print("$ " + " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr.strip()}")


def _create_host_runtime_engine() -> Engine:
    try:
        engine = create_runtime_engine_from_env()
        _ping_engine(engine)
        return engine
    except OperationalError:
        env = dict(os.environ)
        database_url = env.get("DATABASE_URL", "").strip()
        if database_url:
            env["DATABASE_URL"] = _rewrite_local_database_url(database_url)
        else:
            env["POSTGRES_HOST"] = "127.0.0.1"
        engine = create_runtime_engine_from_env(env=env)
        _ping_engine(engine)
        return engine


def _ping_engine(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def _rewrite_local_database_url(database_url: str) -> str:
    for source in ("@postgres:", "@postgres_timescaledb:"):
        if source in database_url:
            return database_url.replace(source, "@127.0.0.1:")
    return database_url


if __name__ == "__main__":
    raise SystemExit(main())
