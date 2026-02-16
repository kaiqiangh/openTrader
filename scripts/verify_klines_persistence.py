from __future__ import annotations

from argparse import ArgumentParser, Namespace
from datetime import UTC, datetime, timedelta
from pathlib import Path
import os
import sys

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.shared.runtime.database import create_runtime_engine_from_env  # noqa: E402
from services.shared.runtime.env_loader import load_dotenv_file  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    load_dotenv_file()
    args = _parse_args(argv)
    exchanges = _parse_exchanges(args.exchanges)
    since = datetime.now(UTC) - timedelta(minutes=max(1, args.minutes))
    engine = _create_host_runtime_engine()

    failures: list[str] = []
    for exchange in exchanges:
        stats = _kline_stats(
            engine=engine,
            exchange=exchange,
            symbol=args.symbol.upper(),
            interval=args.interval,
            since=since,
        )
        if stats["rows"] < args.min_rows:
            failures.append(
                f"{exchange}: expected >= {args.min_rows} rows, found {stats['rows']}"
            )
        latest = stats["latest"]
        if latest is None:
            failures.append(f"{exchange}: no latest timestamp in window")
        elif latest < since:
            failures.append(
                f"{exchange}: latest kline {latest.isoformat()} is older than window start {since.isoformat()}"
            )
        elif latest.tzinfo is None:
            failures.append(f"{exchange}: latest kline timestamp is not timezone-aware")
        if stats["duplicate_open_times"] > 0:
            failures.append(f"{exchange}: found duplicate kline open times in verification window")

        print(
            "kline.stats"
            f" exchange={exchange}"
            f" symbol={args.symbol.upper()}"
            f" interval={args.interval}"
            f" rows={stats['rows']}"
            f" latest={stats['latest'].isoformat() if stats['latest'] is not None else 'none'}"
            f" duplicates={stats['duplicate_open_times']}"
        )

    if failures:
        raise RuntimeError("Kline persistence verification failed: " + "; ".join(failures))

    print(
        "kline.verify.ok"
        f" exchanges={','.join(exchanges)}"
        f" symbol={args.symbol.upper()}"
        f" interval={args.interval}"
        f" window_minutes={args.minutes}"
    )
    return 0


def _parse_args(argv: list[str] | None) -> Namespace:
    parser = ArgumentParser(description="Verify Postgres kline ingestion persistence")
    parser.add_argument("--symbol", default="BTC/USDT", help="symbol to validate")
    parser.add_argument("--interval", default="1m", help="kline interval to validate")
    parser.add_argument(
        "--exchanges",
        default="binance,bitget",
        help="comma-separated exchange list",
    )
    parser.add_argument("--minutes", type=int, default=10, help="freshness lookback window")
    parser.add_argument("--min-rows", type=int, default=1, help="minimum rows expected per exchange")
    return parser.parse_args(argv)


def _parse_exchanges(raw: str) -> tuple[str, ...]:
    parsed = tuple(token.strip().lower() for token in raw.split(",") if token.strip())
    if not parsed:
        raise RuntimeError("--exchanges must include at least one exchange")
    supported = {"binance", "bitget"}
    invalid = sorted(set(parsed) - supported)
    if invalid:
        raise RuntimeError(f"unsupported exchanges: {', '.join(invalid)}")
    return parsed


def _kline_stats(
    *,
    engine: Engine,
    exchange: str,
    symbol: str,
    interval: str,
    since: datetime,
) -> dict[str, object]:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT COUNT(*) AS rows, MAX(time) AS latest
                FROM klines
                WHERE exchange = :exchange
                  AND symbol = :symbol
                  AND "interval" = :interval
                  AND time >= :since
                """
            ),
            {
                "exchange": exchange,
                "symbol": symbol,
                "interval": interval,
                "since": since,
            },
        ).mappings().one()
        duplicate_open_times = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT time
                    FROM klines
                    WHERE exchange = :exchange
                      AND symbol = :symbol
                      AND "interval" = :interval
                      AND time >= :since
                    GROUP BY time
                    HAVING COUNT(*) > 1
                ) dup
                """
            ),
            {
                "exchange": exchange,
                "symbol": symbol,
                "interval": interval,
                "since": since,
            },
        ).scalar_one()

    latest = row.get("latest")
    latest_dt = _coerce_datetime(latest) if latest is not None else None
    return {
        "rows": int(row.get("rows") or 0),
        "latest": latest_dt,
        "duplicate_open_times": int(duplicate_open_times),
    }


def _coerce_datetime(value: object) -> datetime:
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
    raise RuntimeError(f"unable to parse datetime value: {value!r}")


def _create_host_runtime_engine() -> Engine:
    try:
        engine = create_runtime_engine_from_env()
        _ping(engine)
        return engine
    except OperationalError:
        env = dict(os.environ)
        if env.get("DATABASE_URL", "").strip():
            env["DATABASE_URL"] = _rewrite_local_database_url(env["DATABASE_URL"])
        else:
            env["POSTGRES_HOST"] = "127.0.0.1"
        engine = create_runtime_engine_from_env(env=env)
        _ping(engine)
        return engine


def _ping(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def _rewrite_local_database_url(database_url: str) -> str:
    for source in ("@postgres:", "@postgres_timescaledb:"):
        if source in database_url:
            return database_url.replace(source, "@127.0.0.1:")
    return database_url


if __name__ == "__main__":
    raise SystemExit(main())
