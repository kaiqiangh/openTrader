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
            count = _query_count(
                repo_root=repo_root,
                query=(
                    "SELECT COUNT(*) FROM klines "
                    f"WHERE exchange = '{exchange}' "
                    f"AND symbol = '{symbol}' "
                    f"AND interval = '{args.interval}' "
                    f"AND time >= now() - interval '{args.lookback_minutes} minutes'"
                ),
            )
            print(f"klines_count exchange={exchange} symbol={symbol} interval={args.interval} count={count}")
            if count < args.min_rows:
                raise RuntimeError(
                    f"insufficient kline rows for {exchange} {symbol} {args.interval}: expected >= {args.min_rows}, got {count}"
                )

    print("Kline persistence verification passed")
    return 0


def _query_count(*, repo_root: Path, query: str) -> int:
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
    return int(lines[-1]) if lines else 0


def _parse_csv(raw: str) -> tuple[str, ...]:
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    if not values:
        raise RuntimeError("expected at least one CSV value")
    return values


def _parse_args(argv: list[str] | None) -> Namespace:
    parser = ArgumentParser(description="Verify kline persistence across exchanges/symbols")
    parser.add_argument("--exchanges", default="binance,bitget")
    parser.add_argument("--symbols", default="BTC/USDT")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--lookback-minutes", type=int, default=30)
    parser.add_argument("--min-rows", type=int, default=1)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
