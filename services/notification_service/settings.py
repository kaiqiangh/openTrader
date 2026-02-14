from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping

from services.notification_service.models import NotificationSeverity
from services.shared.runtime.env_loader import load_dotenv_file


class NotificationSettingsError(ValueError):
    """Raised when notification worker configuration is invalid."""


@dataclass(frozen=True, slots=True)
class NotificationWorkerSettings:
    enabled: bool
    default_gateway: str
    default_severity: NotificationSeverity
    queue_name: str
    consumer_backend: str
    poll_timeout_seconds: float
    idle_sleep_seconds: float
    dedupe_window_seconds: float
    rate_limit_per_minute: int
    max_attempts: int
    backoff_base_seconds: float
    backoff_multiplier: float
    max_backoff_seconds: float
    gateway_timeout_seconds: float
    observability_max_records: int
    rabbitmq_http_api_url: str
    rabbitmq_username: str
    rabbitmq_password: str
    telegram_bot_token: str | None
    telegram_default_chat_id: str | None


def load_notification_worker_settings(
    *,
    env: Mapping[str, str] | None = None,
) -> NotificationWorkerSettings:
    if env is None:
        load_dotenv_file()
    source = env if env is not None else os.environ

    enabled = _parse_bool(source.get("NOTIFY_ENABLED", "true"))
    default_gateway = _require_non_empty(source, "NOTIFY_DEFAULT_GATEWAY", default="telegram").strip().lower()
    queue_name = _require_non_empty(source, "NOTIFY_QUEUE_NAME", default="notify.events.raw")
    consumer_backend = _require_non_empty(source, "NOTIFY_CONSUMER_BACKEND", default="rabbitmq_http").strip().lower()
    if consumer_backend not in {"rabbitmq_http", "inmemory"}:
        raise NotificationSettingsError("NOTIFY_CONSUMER_BACKEND must be rabbitmq_http or inmemory")

    default_severity = _parse_severity(_require_non_empty(source, "NOTIFICATION_DEFAULT_SEVERITY", default="WARNING"))
    poll_timeout_seconds = _parse_positive_float(source, "NOTIFY_POLL_TIMEOUT_SECONDS", default=1.0)
    idle_sleep_seconds = _parse_positive_float(source, "NOTIFY_IDLE_SLEEP_SECONDS", default=0.5)
    dedupe_window_seconds = _parse_positive_float(source, "NOTIFY_DEDUPE_WINDOW_SECONDS", default=120.0)
    rate_limit_per_minute = _parse_positive_int(source, "NOTIFY_RATE_LIMIT_PER_MIN", default=30)
    max_attempts = _parse_positive_int(source, "NOTIFY_MAX_ATTEMPTS", default=3)
    backoff_base_seconds = _parse_non_negative_float(source, "NOTIFY_BACKOFF_BASE_SECONDS", default=0.2)
    backoff_multiplier = _parse_float(source, "NOTIFY_BACKOFF_MULTIPLIER", default=2.0)
    max_backoff_seconds = _parse_positive_float(source, "NOTIFY_BACKOFF_MAX_SECONDS", default=2.0)
    gateway_timeout_seconds = _parse_positive_float(source, "NOTIFY_GATEWAY_TIMEOUT_SECONDS", default=10.0)
    observability_max_records = _parse_positive_int(source, "NOTIFY_OBSERVABILITY_MAX_RECORDS", default=200)
    rabbitmq_http_api_url = _require_non_empty(
        source,
        "NOTIFY_RABBITMQ_HTTP_API_URL",
        default="http://rabbitmq:15672/api",
    )
    rabbitmq_username = _require_non_empty(
        source,
        "RABBITMQ_DEFAULT_USER",
        default="guest",
    )
    rabbitmq_password = _require_non_empty(
        source,
        "RABBITMQ_DEFAULT_PASS",
        default="guest",
    )
    if backoff_multiplier < 1.0:
        raise NotificationSettingsError("NOTIFY_BACKOFF_MULTIPLIER must be >= 1.0")

    telegram_bot_token = _normalize_optional(source.get("TELEGRAM_BOT_TOKEN"))
    telegram_default_chat_id = _normalize_optional(source.get("TELEGRAM_DEFAULT_CHAT_ID"))
    if enabled and default_gateway == "telegram":
        if _is_placeholder_secret(telegram_bot_token):
            raise NotificationSettingsError("TELEGRAM_BOT_TOKEN is required when telegram gateway is enabled")
        if _is_placeholder_secret(telegram_default_chat_id):
            raise NotificationSettingsError("TELEGRAM_DEFAULT_CHAT_ID is required when telegram gateway is enabled")

    return NotificationWorkerSettings(
        enabled=enabled,
        default_gateway=default_gateway,
        default_severity=default_severity,
        queue_name=queue_name,
        consumer_backend=consumer_backend,
        poll_timeout_seconds=poll_timeout_seconds,
        idle_sleep_seconds=idle_sleep_seconds,
        dedupe_window_seconds=dedupe_window_seconds,
        rate_limit_per_minute=rate_limit_per_minute,
        max_attempts=max_attempts,
        backoff_base_seconds=backoff_base_seconds,
        backoff_multiplier=backoff_multiplier,
        max_backoff_seconds=max_backoff_seconds,
        gateway_timeout_seconds=gateway_timeout_seconds,
        observability_max_records=observability_max_records,
        rabbitmq_http_api_url=rabbitmq_http_api_url,
        rabbitmq_username=rabbitmq_username,
        rabbitmq_password=rabbitmq_password,
        telegram_bot_token=telegram_bot_token,
        telegram_default_chat_id=telegram_default_chat_id,
    )


def _parse_bool(value: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise NotificationSettingsError("NOTIFY_ENABLED must be a boolean value")


def _parse_severity(value: str) -> NotificationSeverity:
    normalized = value.strip().upper()
    if normalized not in {"INFO", "WARNING", "CRITICAL"}:
        raise NotificationSettingsError("NOTIFICATION_DEFAULT_SEVERITY must be INFO/WARNING/CRITICAL")
    return NotificationSeverity(normalized)


def _require_non_empty(source: Mapping[str, str], key: str, *, default: str | None = None) -> str:
    raw = source.get(key, default if default is not None else "")
    value = str(raw).strip()
    if not value:
        raise NotificationSettingsError(f"{key} is required")
    return value


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _is_placeholder_secret(value: str | None) -> bool:
    if value is None:
        return True
    normalized = value.strip().lower()
    return normalized in {"", "changeme", "change_me", "set_me", "<set-me>", "your_token_here"}


def _parse_positive_int(source: Mapping[str, str], key: str, *, default: int) -> int:
    try:
        parsed = int(source.get(key, str(default)))
    except (TypeError, ValueError) as exc:
        raise NotificationSettingsError(f"{key} must be an integer") from exc
    if parsed <= 0:
        raise NotificationSettingsError(f"{key} must be > 0")
    return parsed


def _parse_float(source: Mapping[str, str], key: str, *, default: float) -> float:
    try:
        return float(source.get(key, str(default)))
    except (TypeError, ValueError) as exc:
        raise NotificationSettingsError(f"{key} must be numeric") from exc


def _parse_positive_float(source: Mapping[str, str], key: str, *, default: float) -> float:
    parsed = _parse_float(source, key, default=default)
    if parsed <= 0:
        raise NotificationSettingsError(f"{key} must be > 0")
    return parsed


def _parse_non_negative_float(source: Mapping[str, str], key: str, *, default: float) -> float:
    parsed = _parse_float(source, key, default=default)
    if parsed < 0:
        raise NotificationSettingsError(f"{key} must be >= 0")
    return parsed
