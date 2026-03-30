from __future__ import annotations

from argparse import ArgumentParser, Namespace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import asyncio
import json
import os
import sys
import time
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.shared.runtime.broker import InMemoryTopicBroker  # noqa: E402
from services.shared.runtime.database import create_runtime_engine_from_env  # noqa: E402
from services.shared.runtime.env_loader import load_dotenv_file  # noqa: E402
from services.workers.main import RuntimeWorkerSettings, build_runtime_worker  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    load_dotenv_file()
    args = _parse_args(argv)
    _validate_llm_runtime_env()

    strategy_id = _coerce_uuid(args.strategy_id or os.getenv("STRATEGY_ID", "default-strategy"))
    trace_id = str(uuid.uuid4())
    decision_id = str(uuid.uuid4())

    engine = _create_host_runtime_engine()
    before_total = _scalar_int(
        engine=engine,
        query=text("SELECT COUNT(*) FROM llm_calls"),
        params={},
    )

    broker = InMemoryTopicBroker.from_topology_file(_resolve_topology_path(args.topology_path))
    settings = RuntimeWorkerSettings(
        worker="orchestrator",
        broker_backend="inmemory",
        topology_path=args.topology_path,
        mode=args.mode,
        symbol=args.symbol,
        strategy_id=strategy_id,
        once=True,
        validate_only=False,
        max_idle_cycles=1,
        poll_timeout_seconds=max(0.1, float(args.poll_timeout_seconds)),
        idle_sleep_seconds=0.1,
        bootstrap_topology=False,
        portfolio_base_balance_usd=100000.0,
        require_database=True,
    )
    build = build_runtime_worker(settings=settings, broker=broker, runtime_engine=engine)

    envelope = _build_market_envelope(
        trace_id=trace_id,
        decision_id=decision_id,
        mode=args.mode,
        symbol=args.symbol,
        exchange=args.exchange,
        base_price=float(args.base_price),
    )

    did_work = asyncio.run(
        _run_once(
            broker=broker,
            worker=build.worker,
            envelope=envelope,
            timeout_seconds=max(0.1, float(args.poll_timeout_seconds)),
        )
    )
    if not did_work:
        raise RuntimeError("Orchestrator cycle did not consume the injected market event")

    result = _await_llm_call_persistence(
        engine=engine,
        decision_id=decision_id,
        before_total=before_total,
        timeout_seconds=max(1.0, float(args.wait_timeout_seconds)),
    )
    if result is None:
        raise RuntimeError(
            "LLM smoke trigger did not persist llm_calls for the injected decision. "
            "Verify LLM_RUNTIME_ENABLED=true, LITELLM_BASE_URL is reachable, and strategy_id maps to UUID columns."
        )

    print(
        json.dumps(
            {
                "status": "ok",
                "trace_id": trace_id,
                "decision_id": decision_id,
                "strategy_id": strategy_id,
                "symbol": args.symbol,
                "mode": args.mode,
                "llm_calls_for_decision": result["decision_calls"],
                "llm_calls_total_before": before_total,
                "llm_calls_total_after": result["total_calls"],
                "latest_call": result["latest_call"],
            },
            ensure_ascii=True,
        )
    )
    return 0


def _parse_args(argv: list[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Inject one synthetic market event and force a single orchestrator cycle, "
            "then verify llm_calls persistence in Postgres."
        )
    )
    parser.add_argument("--mode", default="MOCK", choices=("MOCK", "REAL"))
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--strategy-id", default="")
    parser.add_argument("--base-price", type=float, default=50000.0)
    parser.add_argument("--poll-timeout-seconds", type=float, default=2.0)
    parser.add_argument("--wait-timeout-seconds", type=float, default=12.0)
    parser.add_argument("--topology-path", default="config/rabbitmq/topology.json")
    return parser.parse_args(argv)


def _validate_llm_runtime_env() -> None:
    enabled = _parse_bool(os.getenv("LLM_RUNTIME_ENABLED", "false"))
    if not enabled:
        raise RuntimeError("LLM_RUNTIME_ENABLED must be true before running llm smoke trigger")
    base_url = os.getenv("LITELLM_BASE_URL", "").strip()
    if not base_url:
        raise RuntimeError("LITELLM_BASE_URL must be set before running llm smoke trigger")


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise RuntimeError(f"Invalid boolean for env value: {value}")


def _coerce_uuid(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, "default-strategy"))
    try:
        return str(uuid.UUID(candidate))
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, candidate))


def _resolve_topology_path(path: str) -> str:
    topology = Path(path)
    if topology.is_absolute():
        return str(topology)
    return str((_REPO_ROOT / topology).resolve())


def _build_market_envelope(
    *,
    trace_id: str,
    decision_id: str,
    mode: str,
    symbol: str,
    exchange: str,
    base_price: float,
) -> dict[str, Any]:
    best_bid = round(base_price - 2.5, 4)
    best_ask = round(base_price + 2.5, 4)
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    return {
        "trace_id": trace_id,
        "decision_id": decision_id,
        "mode": mode,
        "idempotency_key": f"llm-smoke:{decision_id}",
        "event_type": "market.canonical.orderbook_delta",
        "emitted_at": _utc_now_iso(),
        "payload": {
            "exchange": exchange,
            "symbol": symbol,
            "timestamp_ms": now_ms,
            "bids": [
                {"price": best_bid, "amount": 8.5},
                {"price": round(best_bid - 1.0, 4), "amount": 5.0},
            ],
            "asks": [
                {"price": best_ask, "amount": 7.4},
                {"price": round(best_ask + 1.0, 4), "amount": 4.7},
            ],
            "current_position": 0.0,
            "drawdown_pct": 0.02,
            "news": {
                "summary": "ETF inflows remain stable and spot liquidity is balanced.",
                "sentiment": 0.21,
                "source_count": 3,
            },
        },
        "service": "llm_smoke_trigger",
    }


async def _run_once(
    *, broker: InMemoryTopicBroker, worker: Any, envelope: dict[str, Any], timeout_seconds: float
) -> bool:
    await broker.publish(routing_key="market.canonical", message=dict(envelope))
    return bool(await worker.run_once(timeout_seconds=timeout_seconds))


def _await_llm_call_persistence(
    *,
    engine: Engine,
    decision_id: str,
    before_total: int,
    timeout_seconds: float,
) -> dict[str, Any] | None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        decision_calls = _scalar_int(
            engine=engine,
            query=text("SELECT COUNT(*) FROM llm_calls WHERE decision_id = :decision_id"),
            params={"decision_id": decision_id},
        )
        total_calls = _scalar_int(
            engine=engine,
            query=text("SELECT COUNT(*) FROM llm_calls"),
            params={},
        )
        latest = _fetch_one(
            engine=engine,
            query=text(
                """
                SELECT llm_call_id, provider, model, total_tokens, response_payload->>'status' AS status, created_at
                FROM llm_calls
                WHERE decision_id = :decision_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            params={"decision_id": decision_id},
        )
        if decision_calls >= 1 and total_calls >= before_total + 1:
            return {
                "decision_calls": decision_calls,
                "total_calls": total_calls,
                "latest_call": latest or {},
            }
        time.sleep(0.25)
    return None


def _fetch_one(*, engine: Engine, query: Any, params: dict[str, Any]) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(query, dict(params)).mappings().first()
    if row is None:
        return None
    return {str(key): _json_safe(value) for key, value in dict(row).items()}


def _scalar_int(*, engine: Engine, query: Any, params: dict[str, Any]) -> int:
    with engine.connect() as connection:
        value = connection.execute(query, dict(params)).scalar_one()
    return int(value)


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


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
