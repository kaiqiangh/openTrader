from __future__ import annotations

import pytest

from services.notification_service.settings import NotificationSettingsError
from services.notification_service.worker import RabbitMQHTTPConsumer, RabbitMQHTTPPollingError


@pytest.mark.asyncio
async def test_rabbitmq_http_consumer_declares_missing_queue_once() -> None:
    fetch_calls = 0
    declared_queues: list[str] = []

    def _fetch(api_base_url: str, username: str, password: str, queue_name: str, timeout: float) -> list[dict]:
        nonlocal fetch_calls
        _ = (api_base_url, username, password, queue_name, timeout)
        fetch_calls += 1
        if fetch_calls == 1:
            raise RabbitMQHTTPPollingError(
                status_code=404,
                body='{"error":"not_found","reason":"queue_not_found"}',
            )
        return []

    def _declare(api_base_url: str, username: str, password: str, queue_name: str, timeout: float) -> None:
        _ = (api_base_url, username, password, timeout)
        declared_queues.append(queue_name)

    consumer = RabbitMQHTTPConsumer(
        api_base_url="http://rabbitmq:15672/api",
        username="guest",
        password="guest",
        request_timeout_seconds=1.0,
        fetch_fn=_fetch,
        declare_queue_fn=_declare,
    )

    first = await consumer.consume(queue_name="notify.events.raw", timeout_seconds=0.1)
    second = await consumer.consume(queue_name="notify.events.raw", timeout_seconds=0.1)

    assert first is None
    assert second is None
    assert declared_queues == ["notify.events.raw"]


@pytest.mark.asyncio
async def test_rabbitmq_http_consumer_raises_non_404_poll_errors() -> None:
    def _fetch(api_base_url: str, username: str, password: str, queue_name: str, timeout: float) -> list[dict]:
        _ = (api_base_url, username, password, queue_name, timeout)
        raise RabbitMQHTTPPollingError(status_code=500, body='{"error":"internal"}')

    consumer = RabbitMQHTTPConsumer(
        api_base_url="http://rabbitmq:15672/api",
        username="guest",
        password="guest",
        request_timeout_seconds=1.0,
        fetch_fn=_fetch,
    )

    with pytest.raises(NotificationSettingsError):
        await consumer.consume(queue_name="notify.events.raw", timeout_seconds=0.1)
