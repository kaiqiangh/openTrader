from __future__ import annotations

from argparse import ArgumentParser, Namespace
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import subprocess
import sys
import time


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    smoke_cmd = ["make", "smoke"]
    if args.with_full_profile:
        smoke_cmd = ["uv", "run", "python", "scripts/smoke_test.py", "--with-full-profile"]
    checks = [
        _run_check(
            name="smoke",
            cmd=smoke_cmd,
            cwd=repo_root,
        ),
        _run_check(
            name="runtime_pytests",
            cmd=[
                "uv",
                "run",
                "pytest",
                "tests/test_p10_runtime_worker_entrypoints.py",
                "tests/test_runtime_persistence_adapters.py",
                "tests/test_p10_api_execution_bridge.py",
                "tests/test_smoke_script.py",
                "tests/test_p8_observability_stack.py",
                "-q",
            ],
            cwd=repo_root,
        ),
        _run_check(
            name="real_execution_go_tests",
            cmd=["go", "test", "./..."],
            cwd=repo_root / "services" / "real_execution_go",
            env_overrides={"GOCACHE": "/tmp/go-build"},
        ),
    ]

    overall_status = "passed" if all(check["status"] == "passed" for check in checks) else "failed"
    report = {
        "generated_at": _utc_now_iso(),
        "overall_status": overall_status,
        "checks": checks,
    }
    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Runtime integration gate report written to {report_path}")
    if overall_status != "passed":
        return 1
    return 0


def _run_check(
    *,
    name: str,
    cmd: list[str],
    cwd: Path,
    env_overrides: dict[str, str] | None = None,
) -> dict[str, object]:
    started = time.monotonic()
    env = None
    if env_overrides:
        env = {**os.environ, **env_overrides}

    process = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    duration_seconds = max(0.0, time.monotonic() - started)
    status = "passed" if process.returncode == 0 else "failed"

    if process.stdout.strip():
        print(process.stdout.strip())
    if process.stderr.strip():
        print(process.stderr.strip(), file=sys.stderr)

    return {
        "name": name,
        "status": status,
        "command": cmd,
        "cwd": str(cwd),
        "exit_code": process.returncode,
        "duration_seconds": round(duration_seconds, 3),
    }


def _parse_args(argv: list[str] | None) -> Namespace:
    parser = ArgumentParser(description="Run the dedicated runtime integration validation gate")
    parser.add_argument(
        "--report-path",
        default="artifacts/runtime_integration_gate/latest.json",
        help="path to write JSON gate report",
    )
    parser.add_argument(
        "--with-full-profile",
        action="store_true",
        help="run smoke checks with docker compose full profile",
    )
    return parser.parse_args(argv)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
