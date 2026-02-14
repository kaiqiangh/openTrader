from __future__ import annotations

from pathlib import Path
import os


def load_dotenv_file(path: str | Path = ".env", *, override: bool = False) -> None:
    dotenv_path = Path(path)
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue

        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        value = _parse_value(raw_value.strip())
        if not override and key in os.environ and os.environ[key].strip():
            continue
        os.environ[key] = value


def _parse_value(raw_value: str) -> str:
    if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in {'"', "'"}:
        return raw_value[1:-1]
    if " #" in raw_value:
        return raw_value.split(" #", 1)[0].strip()
    return raw_value
