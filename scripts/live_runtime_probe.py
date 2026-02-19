from __future__ import annotations

from argparse import ArgumentParser, Namespace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import json
import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    started_at = datetime.now(UTC)
    command = _build_probe_command(args)
    result = _run_probe(command=command, timeout_seconds=args.probe_timeout_seconds)

    completed_at = datetime.now(UTC)
    duration_seconds = max(0.0, (completed_at - started_at).total_seconds())
    payload = {
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "completed_at": completed_at.isoformat().replace("+00:00", "Z"),
        "duration_seconds": duration_seconds,
        "overall_status": "ok" if result.returncode == 0 else "failed",
        "command": command,
        "return_code": result.returncode,
        "stdout_tail": _tail_lines(result.stdout, max_lines=120),
        "stderr_tail": _tail_lines(result.stderr, max_lines=120),
    }
    _write_artifact(output_path=Path(args.output), payload=payload)

    if result.returncode != 0:
        print("live_runtime_probe.failed")
        return result.returncode

    print("live_runtime_probe.ok")
    return 0


def _parse_args(argv: list[str] | None) -> Namespace:
    parser = ArgumentParser(description="Nightly runtime live probe wrapper")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--lookback-minutes", type=int, default=20)
    parser.add_argument("--market-exchanges", default="binance,bitget")
    parser.add_argument("--workflow-timeout-seconds", type=float, default=90.0)
    parser.add_argument("--service-wait-timeout", type=float, default=60.0)
    parser.add_argument("--probe-timeout-seconds", type=float, default=900.0)
    parser.add_argument(
        "--output",
        default="artifacts/live_runtime_probe/latest.json",
        help="JSON artifact path written on success/failure",
    )
    parser.add_argument("--skip-compose", action="store_true")
    return parser.parse_args(argv)


def _build_probe_command(args: Namespace) -> list[str]:
    command = [
        sys.executable,
        "scripts/mock_realtime_workflow_test.py",
        "--symbol",
        str(args.symbol),
        "--interval",
        str(args.interval),
        "--lookback-minutes",
        str(int(args.lookback_minutes)),
        "--market-exchanges",
        str(args.market_exchanges),
        "--workflow-timeout-seconds",
        str(float(args.workflow_timeout_seconds)),
        "--service-wait-timeout",
        str(float(args.service_wait_timeout)),
    ]
    if args.skip_compose:
        command.append("--skip-compose")
    return command


def _run_probe(*, command: list[str], timeout_seconds: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        timeout=max(1.0, float(timeout_seconds)),
        capture_output=True,
        text=True,
    )


def _tail_lines(value: str, *, max_lines: int) -> list[str]:
    lines = [line.rstrip() for line in value.splitlines() if line.rstrip()]
    if len(lines) <= max_lines:
        return lines
    return lines[-max_lines:]


def _write_artifact(*, output_path: Path, payload: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
