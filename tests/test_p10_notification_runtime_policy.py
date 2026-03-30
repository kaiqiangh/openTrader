from __future__ import annotations

import pytest

from services.notification_service.settings import (
    NotificationSettingsError,
    load_notification_worker_settings,
)


def _base_env() -> dict[str, str]:
    return {
        "NOTIFY_ENABLED": "true",
        "NOTIFY_DEFAULT_GATEWAY": "telegram",
        "NOTIFICATION_DEFAULT_SEVERITY": "WARNING",
        "NOTIFY_QUEUE_NAME": "notify.events.raw",
        "NOTIFY_POLL_TIMEOUT_SECONDS": "1.0",
        "NOTIFY_IDLE_SLEEP_SECONDS": "0.5",
        "NOTIFY_RATE_LIMIT_PER_MIN": "30",
        "NOTIFY_DEDUPE_WINDOW_SECONDS": "120",
        "NOTIFY_MAX_ATTEMPTS": "3",
        "NOTIFY_BACKOFF_BASE_SECONDS": "0.2",
        "NOTIFY_BACKOFF_MULTIPLIER": "2.0",
        "NOTIFY_BACKOFF_MAX_SECONDS": "2.0",
        "NOTIFY_GATEWAY_TIMEOUT_SECONDS": "10.0",
        "NOTIFY_OBSERVABILITY_MAX_RECORDS": "200",
        "NOTIFY_RABBITMQ_HTTP_API_URL": "http://rabbitmq:15672/api",
        "RABBITMQ_DEFAULT_USER": "guest",
        "RABBITMQ_DEFAULT_PASS": "guest",
        "TELEGRAM_BOT_TOKEN": "bot-token",
        "TELEGRAM_DEFAULT_CHAT_ID": "ops-channel",
    }


def test_notification_settings_reject_inmemory_backend_when_runtime_db_required() -> None:
    env = _base_env()
    env["RUNTIME_REQUIRE_DATABASE"] = "true"
    env["NOTIFY_CONSUMER_BACKEND"] = "inmemory"

    with pytest.raises(NotificationSettingsError):
        load_notification_worker_settings(env=env)


def test_notification_settings_allow_rabbitmq_backend_when_runtime_db_required() -> None:
    env = _base_env()
    env["RUNTIME_REQUIRE_DATABASE"] = "true"
    env["NOTIFY_CONSUMER_BACKEND"] = "rabbitmq_http"

    settings = load_notification_worker_settings(env=env)
    assert settings.consumer_backend == "rabbitmq_http"
    assert settings.runtime_require_database is True
