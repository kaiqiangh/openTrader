from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from services.shared.runtime.rabbitmq_http_broker import (
    RabbitMQHTTPBrokerError,
    RabbitMQHTTPTopicBroker,
)


def _write_topology(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "topology.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_publish_resolves_exchange_from_topology(tmp_path: Path) -> None:
    topology_path = _write_topology(
        tmp_path,
        {
            "bindings": [
                {
                    "exchange": "market.events",
                    "queue": "market.canonical",
                    "routing_key": "market.canonical",
                },
                {
                    "exchange": "notify.events",
                    "queue": "notify.events.raw",
                    "routing_key": "notify.#",
                },
            ]
        },
    )
    captured: dict[str, Any] = {}

    def _publish(
        api_base_url: str,
        username: str,
        password: str,
        exchange_name: str,
        routing_key: str,
        message: dict[str, Any],
        timeout_seconds: float,
    ) -> None:
        captured.update(
            {
                "api_base_url": api_base_url,
                "username": username,
                "password": password,
                "exchange_name": exchange_name,
                "routing_key": routing_key,
                "message": message,
                "timeout_seconds": timeout_seconds,
            }
        )

    broker = RabbitMQHTTPTopicBroker(
        api_base_url="http://rabbitmq:15672/api",
        username="guest",
        password="guest",
        topology_path=topology_path,
        publish_fn=_publish,
        fetch_fn=lambda *args: [],
    )

    await broker.publish(
        routing_key="market.canonical", message={"event_type": "market.canonical.orderbook_delta"}
    )

    assert captured["exchange_name"] == "market.events"
    assert captured["routing_key"] == "market.canonical"
    assert captured["message"]["event_type"] == "market.canonical.orderbook_delta"


@pytest.mark.asyncio
async def test_consume_declares_missing_queue_on_queue_not_found(tmp_path: Path) -> None:
    topology_path = _write_topology(tmp_path, {"bindings": []})
    calls = {"declares": 0}

    def _fetch(*args) -> list[dict[str, Any]]:
        raise RabbitMQHTTPBrokerError(
            message="queue missing",
            status_code=404,
            body='{"error":"not_found","reason":"queue_not_found"}',
        )

    def _declare_queue(*args) -> None:
        calls["declares"] += 1

    broker = RabbitMQHTTPTopicBroker(
        api_base_url="http://rabbitmq:15672/api",
        username="guest",
        password="guest",
        topology_path=topology_path,
        fetch_fn=_fetch,
        declare_queue_fn=_declare_queue,
    )

    first = await broker.consume(queue_name="notify.events.raw", timeout_seconds=0.1)
    second = await broker.consume(queue_name="notify.events.raw", timeout_seconds=0.1)

    assert first is None
    assert second is None
    assert calls["declares"] == 1


@pytest.mark.asyncio
async def test_bootstrap_topology_declares_exchanges_queues_and_bindings_once(
    tmp_path: Path,
) -> None:
    topology_path = _write_topology(
        tmp_path,
        {
            "exchanges": [{"name": "market.events"}, {"name": "notify.events"}],
            "queues": [{"name": "market.canonical"}, {"name": "notify.events.raw"}],
            "bindings": [
                {
                    "exchange": "market.events",
                    "queue": "market.canonical",
                    "routing_key": "market.canonical",
                },
                {
                    "exchange": "notify.events",
                    "queue": "notify.events.raw",
                    "routing_key": "notify.#",
                },
            ],
        },
    )
    calls = {"exchange": 0, "queue": 0, "binding": 0}

    def _declare_exchange(*args) -> None:
        calls["exchange"] += 1

    def _declare_queue(*args) -> None:
        calls["queue"] += 1

    def _bind_queue(*args) -> None:
        calls["binding"] += 1

    broker = RabbitMQHTTPTopicBroker(
        api_base_url="http://rabbitmq:15672/api",
        username="guest",
        password="guest",
        topology_path=topology_path,
        fetch_fn=lambda *args: [],
        declare_exchange_fn=_declare_exchange,
        declare_queue_fn=_declare_queue,
        bind_queue_fn=_bind_queue,
    )

    await broker.bootstrap_topology()
    await broker.bootstrap_topology()

    assert calls["exchange"] == 2
    assert calls["queue"] == 2
    assert calls["binding"] == 2
