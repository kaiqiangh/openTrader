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
    "REDIS_PASSWORD",
    "RABBITMQ_DEFAULT_USER",
    "RABBITMQ_DEFAULT_PASS",
    "EXCHANGE_DEFAULT",
    "MARKET_EXCHANGES",
    "MARKET_SYMBOLS",
    "MARKET_DATA_FETCH_MODE",
    "MARKET_DATA_REST_POLL_SECONDS",
    "ORDERBOOK_SNAPSHOT_INTERVAL_SECONDS",
    "KLINE_INTERVALS",
    "KLINE_POLL_INTERVAL_SECONDS",
    "KLINE_FETCH_LIMIT",
    "EXECUTION_MODE_DEFAULT",
    "SIMULATION_SLIPPAGE_BPS",
    "SIMULATION_FEE_BPS",
    "NEWS_SOURCE_MODE",
    "NEWS_RSS_FEEDS",
    "NEWS_FETCH_TIMEOUT_SECONDS",
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
    "JWT_PRIVATE_KEY",
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
            print(
                "TELEGRAM_BOT_TOKEN is required when NOTIFY_ENABLED=true and NOTIFY_DEFAULT_GATEWAY=telegram"
            )
            return 1
        if _is_placeholder_secret(os.getenv("TELEGRAM_DEFAULT_CHAT_ID")):
            print(
                "TELEGRAM_DEFAULT_CHAT_ID is required when NOTIFY_ENABLED=true and NOTIFY_DEFAULT_GATEWAY=telegram"
            )
            return 1

    if notify_enabled and default_gateway == "email":
        if not os.getenv("EMAIL_SMTP_HOST"):
            print("EMAIL_SMTP_HOST is required when NOTIFY_DEFAULT_GATEWAY=email")
            return 1
        if not os.getenv("EMAIL_FROM_ADDRESS"):
            print("EMAIL_FROM_ADDRESS is required when NOTIFY_DEFAULT_GATEWAY=email")
            return 1
        if not os.getenv("EMAIL_DEFAULT_RECIPIENTS"):
            print("EMAIL_DEFAULT_RECIPIENTS is required when NOTIFY_DEFAULT_GATEWAY=email")
            return 1

    if notify_enabled and default_gateway == "webhook":
        if not os.getenv("WEBHOOK_URL"):
            print("WEBHOOK_URL is required when NOTIFY_DEFAULT_GATEWAY=webhook")
            return 1

    if (
        notify_enabled
        and consumer_backend == "rabbitmq_http"
        and not os.getenv("NOTIFY_RABBITMQ_HTTP_API_URL")
    ):
        print(
            "NOTIFY_RABBITMQ_HTTP_API_URL is required when NOTIFY_ENABLED=true and rabbitmq_http backend is selected"
        )
        return 1

    exchange_default = os.getenv("EXCHANGE_DEFAULT", "").strip().lower()
    if exchange_default not in {"binance", "bitget"}:
        print("EXCHANGE_DEFAULT must be binance or bitget")
        return 1

    market_exchanges = tuple(
        token.strip().lower()
        for token in os.getenv("MARKET_EXCHANGES", "").split(",")
        if token.strip()
    )
    if not market_exchanges:
        print("MARKET_EXCHANGES must include at least one exchange")
        return 1
    if any(exchange not in {"binance", "bitget"} for exchange in market_exchanges):
        print("MARKET_EXCHANGES entries must be binance or bitget")
        return 1

    market_symbols = tuple(
        token.strip().upper()
        for token in os.getenv("MARKET_SYMBOLS", "").split(",")
        if token.strip()
    )
    if not market_symbols:
        print("MARKET_SYMBOLS must include at least one symbol")
        return 1

    market_fetch_mode = os.getenv("MARKET_DATA_FETCH_MODE", "").strip().lower()
    if market_fetch_mode not in {"rest", "restful", "http", "websocket", "ws"}:
        print("MARKET_DATA_FETCH_MODE must be rest or websocket")
        return 1

    rest_poll_seconds_raw = os.getenv("MARKET_DATA_REST_POLL_SECONDS", "").strip()
    try:
        rest_poll_seconds = float(rest_poll_seconds_raw)
    except ValueError:
        print("MARKET_DATA_REST_POLL_SECONDS must be a positive number")
        return 1
    if rest_poll_seconds <= 0:
        print("MARKET_DATA_REST_POLL_SECONDS must be a positive number")
        return 1

    orderbook_interval_raw = os.getenv("ORDERBOOK_SNAPSHOT_INTERVAL_SECONDS", "").strip()
    try:
        orderbook_interval = float(orderbook_interval_raw)
    except ValueError:
        print("ORDERBOOK_SNAPSHOT_INTERVAL_SECONDS must be a positive number")
        return 1
    if orderbook_interval <= 0:
        print("ORDERBOOK_SNAPSHOT_INTERVAL_SECONDS must be a positive number")
        return 1

    kline_intervals = tuple(
        token.strip().lower()
        for token in os.getenv("KLINE_INTERVALS", "").split(",")
        if token.strip()
    )
    if not kline_intervals:
        print("KLINE_INTERVALS must include at least one interval")
        return 1

    kline_poll_raw = os.getenv("KLINE_POLL_INTERVAL_SECONDS", "").strip()
    try:
        kline_poll = float(kline_poll_raw)
    except ValueError:
        print("KLINE_POLL_INTERVAL_SECONDS must be a positive number")
        return 1
    if kline_poll <= 0:
        print("KLINE_POLL_INTERVAL_SECONDS must be a positive number")
        return 1

    kline_fetch_limit_raw = os.getenv("KLINE_FETCH_LIMIT", "").strip()
    try:
        kline_fetch_limit = int(kline_fetch_limit_raw)
    except ValueError:
        print("KLINE_FETCH_LIMIT must be a positive integer")
        return 1
    if kline_fetch_limit <= 0:
        print("KLINE_FETCH_LIMIT must be a positive integer")
        return 1

    news_source_mode = os.getenv("NEWS_SOURCE_MODE", "").strip().lower()
    if news_source_mode not in {"real", "mock"}:
        print("NEWS_SOURCE_MODE must be real or mock")
        return 1
    if news_source_mode == "real":
        feed_urls = tuple(
            token.strip() for token in os.getenv("NEWS_RSS_FEEDS", "").split(",") if token.strip()
        )
        if not feed_urls:
            print("NEWS_RSS_FEEDS must include at least one URL when NEWS_SOURCE_MODE=real")
            return 1
    news_fetch_timeout_raw = os.getenv("NEWS_FETCH_TIMEOUT_SECONDS", "").strip()
    try:
        news_fetch_timeout = float(news_fetch_timeout_raw)
    except ValueError:
        print("NEWS_FETCH_TIMEOUT_SECONDS must be a positive number")
        return 1
    if news_fetch_timeout <= 0:
        print("NEWS_FETCH_TIMEOUT_SECONDS must be a positive number")
        return 1

    litellm_model_error = _validate_litellm_model_binding(
        base_url=os.getenv("LITELLM_BASE_URL", ""),
        model=os.getenv("LITELLM_MODEL", ""),
    )
    if litellm_model_error:
        print(litellm_model_error)
        return 1

    if not _is_valid_aes256_key(os.getenv("ENCRYPTION_KEY_BASE64", "")):
        print(
            "ENCRYPTION_KEY_BASE64 must be a valid base64 string that decodes to 32 bytes (AES-256-GCM key)"
        )
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


def _validate_litellm_model_binding(*, base_url: str, model: str) -> str | None:
    normalized_base = base_url.strip().lower()
    normalized_model = model.strip()
    if not normalized_base or not normalized_model:
        return None
    if "api.deepseek.com" in normalized_base and normalized_model.startswith("deepseek/"):
        return (
            "LITELLM_MODEL must be deepseek-chat when LITELLM_BASE_URL points to api.deepseek.com"
        )
    return None


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
