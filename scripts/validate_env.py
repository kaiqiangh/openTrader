from __future__ import annotations

import base64
import os
from pathlib import Path

REQUIRED_KEYS = [
    "APP_ENV",
    "APP_NAME",
    "LOG_LEVEL",
    "API_HOST",
    "API_PORT",
    "API_READ_ONLY_MODE",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "REDIS_URL",
    "RABBITMQ_URL",
    "RABBITMQ_DEFAULT_USER",
    "RABBITMQ_DEFAULT_PASS",
    "EXECUTION_MODE_DEFAULT",
    "SIMULATION_SLIPPAGE_BPS",
    "SIMULATION_FEE_BPS",
    "NOTIFY_ENABLED",
    "NOTIFY_DEFAULT_GATEWAY",
    "NOTIFICATION_DEFAULT_SEVERITY",
    "NOTIFY_QUEUE_NAME",
    "NOTIFY_CONSUMER_BACKEND",
    "NOTIFY_GATEWAY_TIMEOUT_SECONDS",
    "NOTIFY_RATE_LIMIT_PER_MIN",
    "NOTIFY_DEDUPE_WINDOW_SECONDS",
    "NOTIFY_MAX_ATTEMPTS",
    "NOTIFY_BACKOFF_BASE_SECONDS",
    "NOTIFY_BACKOFF_MULTIPLIER",
    "NOTIFY_BACKOFF_MAX_SECONDS",
    "NOTIFY_OBSERVABILITY_MAX_RECORDS",
    "ENCRYPTION_KEY_BASE64",
    "JWT_SECRET_KEY",
]


def main() -> int:
    load_dotenv_file()
    missing = [k for k in REQUIRED_KEYS if not os.getenv(k)]
    if missing:
        print(f"Missing required env keys: {', '.join(missing)}")
        return 1

    try:
        notify_enabled = _parse_bool(os.getenv("NOTIFY_ENABLED", "true"))
    except ValueError as exc:
        print(str(exc))
        return 1
    try:
        _parse_bool(os.getenv("API_READ_ONLY_MODE", "true"))
    except ValueError as exc:
        print(str(exc).replace("NOTIFY_ENABLED", "API_READ_ONLY_MODE"))
        return 1
    default_gateway = os.getenv("NOTIFY_DEFAULT_GATEWAY", "telegram").strip().lower()
    consumer_backend = os.getenv("NOTIFY_CONSUMER_BACKEND", "rabbitmq_http").strip().lower()
    if consumer_backend not in {"rabbitmq_http", "inmemory"}:
        print("NOTIFY_CONSUMER_BACKEND must be rabbitmq_http or inmemory")
        return 1

    if notify_enabled and default_gateway == "telegram":
        if _is_placeholder_secret(os.getenv("TELEGRAM_BOT_TOKEN")):
            print("TELEGRAM_BOT_TOKEN is required when NOTIFY_ENABLED=true and NOTIFY_DEFAULT_GATEWAY=telegram")
            return 1
        if _is_placeholder_secret(os.getenv("TELEGRAM_DEFAULT_CHAT_ID")):
            print("TELEGRAM_DEFAULT_CHAT_ID is required when NOTIFY_ENABLED=true and NOTIFY_DEFAULT_GATEWAY=telegram")
            return 1

    if notify_enabled and consumer_backend == "rabbitmq_http" and not os.getenv("NOTIFY_RABBITMQ_HTTP_API_URL"):
        print("NOTIFY_RABBITMQ_HTTP_API_URL is required when NOTIFY_ENABLED=true and rabbitmq_http backend is selected")
        return 1

    if not _is_valid_aes256_key(os.getenv("ENCRYPTION_KEY_BASE64", "")):
        print("ENCRYPTION_KEY_BASE64 must be a valid base64 string that decodes to 32 bytes (AES-256-GCM key)")
        return 1
    print("Environment validation passed")
    return 0


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError("NOTIFY_ENABLED must be a boolean value")


def _is_placeholder_secret(value: str | None) -> bool:
    if value is None:
        return True
    normalized = value.strip().lower()
    return normalized in {"", "changeme", "change_me", "set_me", "<set-me>", "your_token_here"}


def _is_valid_aes256_key(value: str) -> bool:
    normalized = value.strip()
    if not normalized:
        return False
    try:
        decoded = base64.b64decode(normalized, validate=True)
    except (ValueError, TypeError):
        return False
    return len(decoded) == 32


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

        value = _parse_env_value(raw_value.strip())
        if not override and key in os.environ and os.environ[key].strip():
            continue
        os.environ[key] = value


def _parse_env_value(raw_value: str) -> str:
    if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in {'"', "'"}:
        return raw_value[1:-1]
    if " #" in raw_value:
        return raw_value.split(" #", 1)[0].strip()
    return raw_value


if __name__ == "__main__":
    raise SystemExit(main())
