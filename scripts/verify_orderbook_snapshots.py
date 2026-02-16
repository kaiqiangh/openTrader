from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path
import os
import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]

    for exchange in _parse_csv(args.exchanges):
        for symbol in _parse_csv(args.symbols):
            latest_age_seconds = _query_float(
                repo_root=repo_root,
                query=(
                    "SELECT EXTRACT(EPOCH FROM (now() - MAX(snapshot_time))) "
                    "FROM orderbook_snapshots "
                    f"WHERE exchange = '{exchange}' AND symbol = '{symbol}'"
                ),
            )
            row_count = _query_int(
                repo_root=repo_root,
                query=(
                    "SELECT COUNT(*) FROM orderbook_snapshots "
                    f"WHERE exchange = '{exchange}' "
                    f"AND symbol = '{symbol}' "
                    f"AND snapshot_time >= now() - interval '{args.lookback_minutes} minutes'"
                ),
            )
            print(
                f"orderbook exchange={exchange} symbol={symbol} rows={row_count} age_s={latest_age_seconds:.1f}"
            )
            if row_count < args.min_rows:
                raise RuntimeError(
                    f"insufficient orderbook snapshots for {exchange} {symbol}: expected >= {args.min_rows}, got {row_count}"
                )
            if latest_age_seconds > args.max_age_seconds:
                raise RuntimeError(
                    f"latest orderbook snapshot too old for {exchange} {symbol}: {latest_age_seconds:.1f}s"
                )

    print("Orderbook snapshot verification passed")
    return 0


def _query_int(*, repo_root: Path, query: str) -> int:
    value = _query_scalar(repo_root=repo_root, query=query)
    return int(float(value)) if value else 0


def _query_float(*, repo_root: Path, query: str) -> float:
    value = _query_scalar(repo_root=repo_root, query=query)
    return float(value) if value else 999999.0


def _query_scalar(*, repo_root: Path, query: str) -> str:
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
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _parse_csv(raw: str) -> tuple[str, ...]:
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    if not values:
        raise RuntimeError("expected at least one CSV value")
    return values


def _parse_args(argv: list[str] | None) -> Namespace:
    parser = ArgumentParser(description="Verify orderbook snapshot recency + density")
    parser.add_argument("--exchanges", default="binance,bitget")
    parser.add_argument("--symbols", default="BTC/USDT")
    parser.add_argument("--lookback-minutes", type=int, default=30)
    parser.add_argument("--min-rows", type=int, default=1)
    parser.add_argument(
        "--max-age-seconds",
        type=int,
        default=int(os.getenv("ORDERBOOK_SNAPSHOT_INTERVAL_SECONDS", "180")) * 2,
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
