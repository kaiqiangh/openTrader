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
        stats = _snapshot_stats(
            engine=engine,
            exchange=exchange,
            symbol=args.symbol.upper(),
            since=since,
        )

        if stats["rows"] == 0:
            failures.append(f"{exchange}: no snapshots in verification window")
            _print_stats(exchange=exchange, symbol=args.symbol.upper(), stats=stats)
            continue

        latest = stats["latest"]
        if latest is None or latest < since:
            failures.append(f"{exchange}: latest snapshot is stale")

        expected_gap = max(1, int(args.expected_interval_seconds))
        tolerance = max(int(args.tolerance_seconds), int(expected_gap * 0.5))
        max_allowed_gap = expected_gap + tolerance

        gaps = stats["gaps_seconds"]
        if gaps:
            largest_gap = max(gaps)
            if largest_gap > max_allowed_gap:
                failures.append(
                    f"{exchange}: largest snapshot gap {largest_gap}s exceeds allowed {max_allowed_gap}s"
                )

        if stats["duplicate_timestamps"] > 0:
            failures.append(f"{exchange}: found duplicate snapshot timestamps")

        if expected_gap <= args.minutes * 60 and stats["rows"] < 2:
            failures.append(
                f"{exchange}: expected at least 2 snapshots in window, found {stats['rows']}"
            )

        _print_stats(exchange=exchange, symbol=args.symbol.upper(), stats=stats)

    if failures:
        raise RuntimeError("Orderbook snapshot verification failed: " + "; ".join(failures))

    print(
        "orderbook.verify.ok"
        f" exchanges={','.join(exchanges)}"
        f" symbol={args.symbol.upper()}"
        f" window_minutes={args.minutes}"
        f" expected_interval_seconds={args.expected_interval_seconds}"
    )
    return 0


def _parse_args(argv: list[str] | None) -> Namespace:
    parser = ArgumentParser(description="Verify Postgres orderbook snapshot cadence")
    parser.add_argument("--symbol", default="BTC/USDT", help="symbol to validate")
    parser.add_argument(
        "--exchanges",
        default="binance,bitget",
        help="comma-separated exchange list",
    )
    parser.add_argument("--minutes", type=int, default=10, help="freshness lookback window")
    parser.add_argument(
        "--expected-interval-seconds",
        type=int,
        default=180,
        help="expected snapshot interval",
    )
    parser.add_argument(
        "--tolerance-seconds",
        type=int,
        default=45,
        help="allowed interval drift before failure",
    )
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


def _snapshot_stats(
    *, engine: Engine, exchange: str, symbol: str, since: datetime
) -> dict[str, object]:
    with engine.connect() as connection:
        rows = (
            connection.execute(
                text(
                    """
                SELECT snapshot_time
                FROM orderbook_snapshots
                WHERE exchange = :exchange
                  AND symbol = :symbol
                  AND snapshot_time >= :since
                ORDER BY snapshot_time ASC
                """
                ),
                {"exchange": exchange, "symbol": symbol, "since": since},
            )
            .scalars()
            .all()
        )
        duplicate_timestamps = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT snapshot_time
                    FROM orderbook_snapshots
                    WHERE exchange = :exchange
                      AND symbol = :symbol
                      AND snapshot_time >= :since
                    GROUP BY snapshot_time
                    HAVING COUNT(*) > 1
                ) dup
                """
            ),
            {"exchange": exchange, "symbol": symbol, "since": since},
        ).scalar_one()

    timestamps = [_coerce_datetime(item) for item in rows]
    gaps: list[int] = []
    for idx in range(1, len(timestamps)):
        gap_seconds = int((timestamps[idx] - timestamps[idx - 1]).total_seconds())
        gaps.append(max(0, gap_seconds))

    latest = timestamps[-1] if timestamps else None
    return {
        "rows": len(timestamps),
        "latest": latest,
        "gaps_seconds": tuple(gaps),
        "duplicate_timestamps": int(duplicate_timestamps),
    }


def _print_stats(*, exchange: str, symbol: str, stats: dict[str, object]) -> None:
    gaps = list(stats["gaps_seconds"])
    latest = stats["latest"]
    print(
        "orderbook.stats"
        f" exchange={exchange}"
        f" symbol={symbol}"
        f" rows={stats['rows']}"
        f" latest={latest.isoformat() if isinstance(latest, datetime) else 'none'}"
        f" largest_gap_seconds={max(gaps) if gaps else 0}"
        f" duplicate_timestamps={stats['duplicate_timestamps']}"
    )


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
