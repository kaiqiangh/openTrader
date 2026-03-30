#!/usr/bin/env python3
"""Pre-commit hook: detect real secrets in staged .env files.

Run: python scripts/check_env_secrets.py .env
Exit 0 = clean, Exit 1 = secrets detected.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Patterns that indicate real secrets (not placeholders)
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("DeepSeek API key", re.compile(r"^sk-[a-f0-9]{20,}$", re.IGNORECASE)),
    ("Telegram bot token", re.compile(r"^\d{8,}:[A-Za-z0-9_-]{30,}$")),
    ("Base64 32-byte key", re.compile(r"^[A-Za-z0-9+/]{40,}={0,2}$")),
    ("Hex 32+ byte key", re.compile(r"^[a-f0-9]{64,}$", re.IGNORECASE)),
]

_PLACEHOLDER_VALUES = {
    "",
    "change_me",
    "guest",
    "<CHANGE_ME>",
    "your-secret-here",
    "bot",
    "chat",
    "admin",
}


def check_env_file(path: Path) -> list[str]:
    if not path.exists():
        return []

    findings: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.split("#")[0].strip()  # strip inline comments

        if value in _PLACEHOLDER_VALUES:
            continue

        for label, pattern in _SECRET_PATTERNS:
            if pattern.match(value):
                findings.append(f"  ⚠️  {key} looks like a real {label}")
                break

    return findings


def main() -> int:
    targets = sys.argv[1:] or [".env"]
    has_findings = False

    for target in targets:
        path = Path(target)
        findings = check_env_file(path)
        if findings:
            has_findings = True
            print(f"🔍 {path}:")
            for finding in findings:
                print(finding)

    if has_findings:
        print("\n❌ Real secrets detected. Use .env.example for placeholders.")
        print("   If this is intentional, run: git commit --no-verify")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
