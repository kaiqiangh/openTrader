from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import uuid

import pytest

from services.notification_service.settings import NotificationSettingsError, load_notification_worker_settings
from services.notification_service.worker import (
    InMemoryNotificationEnvelopeConsumer,
    NotificationWorker,
    build_notification_worker_from_settings,
)


def _envelope(*, event_type: str) -> dict[str, object]:
    return {
        "trace_id": str(uuid.uuid4()),
        "decision_id": str(uuid.uuid4()),
        "mode": "MOCK",
        "idempotency_key": f"event:{event_type}:{uuid.uuid4()}",
        "event_type": event_type,
        "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "payload": {"strategy_id": "btc-momentum", "symbol": "BTC/USDT", "reason": "test"},
        "service": "tests",
    }


def _base_env() -> dict[str, str]:
    return {
        "NOTIFY_ENABLED": "true",
        "NOTIFY_DEFAULT_GATEWAY": "telegram",
        "NOTIFICATION_DEFAULT_SEVERITY": "WARNING",
        "NOTIFY_QUEUE_NAME": "notify.events.raw",
        "NOTIFY_CONSUMER_BACKEND": "inmemory",
        "NOTIFY_POLL_TIMEOUT_SECONDS": "0.01",
        "NOTIFY_IDLE_SLEEP_SECONDS": "0.01",
        "NOTIFY_RATE_LIMIT_PER_MIN": "30",
        "NOTIFY_DEDUPE_WINDOW_SECONDS": "120",
        "NOTIFY_MAX_ATTEMPTS": "3",
        "NOTIFY_BACKOFF_BASE_SECONDS": "0.1",
        "NOTIFY_BACKOFF_MULTIPLIER": "2.0",
        "NOTIFY_BACKOFF_MAX_SECONDS": "1.0",
        "NOTIFY_GATEWAY_TIMEOUT_SECONDS": "10.0",
        "NOTIFY_OBSERVABILITY_MAX_RECORDS": "200",
        "NOTIFY_RABBITMQ_HTTP_API_URL": "http://rabbitmq:15672/api",
        "RABBITMQ_DEFAULT_USER": "guest",
        "RABBITMQ_DEFAULT_PASS": "guest",
        "TELEGRAM_BOT_TOKEN": "bot-token",
        "TELEGRAM_DEFAULT_CHAT_ID": "12345",
    }


def test_notification_settings_requires_telegram_secrets_when_enabled() -> None:
    env = _base_env()
    env["TELEGRAM_BOT_TOKEN"] = ""
    with pytest.raises(NotificationSettingsError):
        load_notification_worker_settings(env=env)


@pytest.mark.asyncio
async def test_notification_worker_inmemory_backend_processes_message() -> None:
    env = _base_env()
    env["NOTIFY_DEFAULT_GATEWAY"] = "webhook"
    settings = load_notification_worker_settings(env=env)
    worker = build_notification_worker_from_settings(settings=settings)

    assert isinstance(worker, NotificationWorker)
    assert isinstance(worker.consumer, InMemoryNotificationEnvelopeConsumer)
    await worker.consumer.publish(routing_key="notify.events.raw", message=_envelope(event_type="notify.risk.event"))

    result = await worker.run_once()
    assert result is not None
    assert len(result.results) == 1
    assert result.results[0].status == "DELIVERED"


def test_compose_and_env_include_notification_worker_wiring() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    env_example = Path(".env.example").read_text(encoding="utf-8")

    assert "notification_worker:" in compose
    assert "services.notification_service.worker" in compose
    assert "NOTIFY_ENABLED" in compose
    assert "NOTIFY_QUEUE_NAME" in compose
    assert "NOTIFY_CONSUMER_BACKEND" in compose

    assert "NOTIFY_ENABLED=" in env_example
    assert "NOTIFY_QUEUE_NAME=" in env_example
    assert "NOTIFY_CONSUMER_BACKEND=" in env_example
    assert "NOTIFY_RABBITMQ_HTTP_API_URL=" in env_example
