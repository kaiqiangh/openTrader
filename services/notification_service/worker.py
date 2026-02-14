from __future__ import annotations

from argparse import ArgumentParser, Namespace
from asyncio import run as asyncio_run
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib import error, parse, request
import asyncio
import base64
import json

from services.notification_service.event_intake import NotificationEventIntake
from services.notification_service.gateway_dispatch import GatewayDispatcher, InMemoryGateway
from services.notification_service.models import NotificationPreference, NotificationProcessingResult
from services.notification_service.observability import NotificationObservabilityCollector
from services.notification_service.policy_router import NotificationPolicyRouter
from services.notification_service.service import NotificationService
from services.notification_service.settings import NotificationSettingsError, NotificationWorkerSettings, load_notification_worker_settings
from services.notification_service.telegram_gateway import TelegramGateway, TelegramGatewayConfig
from services.shared.runtime.broker import InMemoryTopicBroker


class NotificationEnvelopeConsumer(Protocol):
    async def consume(self, *, queue_name: str, timeout_seconds: float) -> Mapping[str, Any] | None: ...


class InMemoryNotificationEnvelopeConsumer:
    def __init__(self, *, broker: InMemoryTopicBroker) -> None:
        self.broker = broker

    @classmethod
    def from_topology_file(cls, path: str) -> InMemoryNotificationEnvelopeConsumer:
        return cls(broker=InMemoryTopicBroker.from_topology_file(path))

    async def consume(self, *, queue_name: str, timeout_seconds: float) -> Mapping[str, Any] | None:
        return await self.broker.consume(queue_name=queue_name, timeout_seconds=timeout_seconds)

    async def publish(self, *, routing_key: str, message: Mapping[str, Any]) -> None:
        await self.broker.publish(routing_key=routing_key, message=dict(message))


RabbitMQHTTPFetchFn = Callable[[str, str, str, str, float], list[dict[str, Any]]]


class RabbitMQHTTPConsumer:
    def __init__(
        self,
        *,
        api_base_url: str,
        username: str,
        password: str,
        request_timeout_seconds: float,
        fetch_fn: RabbitMQHTTPFetchFn | None = None,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.username = username
        self.password = password
        self.request_timeout_seconds = request_timeout_seconds
        self._fetch_fn = fetch_fn or _default_rabbitmq_http_fetch

    async def consume(self, *, queue_name: str, timeout_seconds: float) -> Mapping[str, Any] | None:
        _ = timeout_seconds
        rows = await asyncio.to_thread(
            self._fetch_fn,
            self.api_base_url,
            self.username,
            self.password,
            queue_name,
            self.request_timeout_seconds,
        )
        if not rows:
            return None
        payload = rows[0].get("payload")
        if isinstance(payload, Mapping):
            return dict(payload)
        if isinstance(payload, str):
            parsed = json.loads(payload)
            if isinstance(parsed, Mapping):
                return dict(parsed)
        raise NotificationSettingsError("RabbitMQ HTTP payload is not a JSON object envelope")


@dataclass(slots=True)
class NotificationWorker:
    consumer: NotificationEnvelopeConsumer
    service: NotificationService
    queue_name: str
    poll_timeout_seconds: float

    async def run_once(self) -> NotificationProcessingResult | None:
        envelope = await self.consumer.consume(
            queue_name=self.queue_name,
            timeout_seconds=self.poll_timeout_seconds,
        )
        if envelope is None:
            return None
        return await self.service.process_envelope(envelope)


def build_notification_worker_from_settings(
    *,
    settings: NotificationWorkerSettings,
    topology_path: str = "config/rabbitmq/topology.json",
) -> NotificationWorker:
    gateways = {
        settings.default_gateway: _build_gateway(settings=settings),
    }
    service = NotificationService(
        intake=NotificationEventIntake(),
        policy_router=NotificationPolicyRouter(
            preferences=(
                NotificationPreference(
                    user_id="ops-default",
                    min_severity=settings.default_severity,
                    gateways=(settings.default_gateway,),
                ),
            ),
            dedupe_window_seconds=settings.dedupe_window_seconds,
            rate_limit_per_minute=settings.rate_limit_per_minute,
        ),
        dispatcher=GatewayDispatcher(
            gateways=gateways,
            max_attempts=settings.max_attempts,
            backoff_base_seconds=settings.backoff_base_seconds,
            backoff_multiplier=settings.backoff_multiplier,
            max_backoff_seconds=settings.max_backoff_seconds,
        ),
        observability=NotificationObservabilityCollector(
            max_records=settings.observability_max_records,
        ),
    )
    consumer: NotificationEnvelopeConsumer
    if settings.consumer_backend == "inmemory":
        consumer = InMemoryNotificationEnvelopeConsumer.from_topology_file(path=topology_path)
    else:
        consumer = RabbitMQHTTPConsumer(
            api_base_url=settings.rabbitmq_http_api_url,
            username=settings.rabbitmq_username,
            password=settings.rabbitmq_password,
            request_timeout_seconds=settings.poll_timeout_seconds,
        )
    return NotificationWorker(
        consumer=consumer,
        service=service,
        queue_name=settings.queue_name,
        poll_timeout_seconds=settings.poll_timeout_seconds,
    )


async def run_worker_loop(
    *,
    settings: NotificationWorkerSettings,
    once: bool = False,
    max_idle_cycles: int = 0,
) -> int:
    if not settings.enabled:
        print("Notification worker disabled by NOTIFY_ENABLED=false")
        return 0

    worker = build_notification_worker_from_settings(settings=settings)
    idle_cycles = 0
    while True:
        result = await worker.run_once()
        if result is None:
            idle_cycles += 1
            if once:
                return 0
            if max_idle_cycles > 0 and idle_cycles >= max_idle_cycles:
                return 0
            await asyncio.sleep(settings.idle_sleep_seconds)
            continue

        idle_cycles = 0
        print(
            f"processed notification event={result.event.event_type} "
            f"severity={result.event.severity.value} results={len(result.results)}"
        )
        if once:
            return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        settings = load_notification_worker_settings()
    except NotificationSettingsError as exc:
        print(f"Notification worker startup validation failed: {exc}")
        return 1

    if args.validate_only:
        print("Notification worker startup validation passed")
        return 0

    return asyncio_run(
        run_worker_loop(
            settings=settings,
            once=args.once,
            max_idle_cycles=args.max_idle_cycles,
        )
    )


def _build_gateway(*, settings: NotificationWorkerSettings) -> InMemoryGateway | TelegramGateway:
    if settings.default_gateway != "telegram":
        return InMemoryGateway(name=settings.default_gateway)

    if not settings.telegram_bot_token or not settings.telegram_default_chat_id:
        raise NotificationSettingsError("telegram gateway enabled but telegram secrets are missing")

    return TelegramGateway(
        config=TelegramGatewayConfig(
            bot_token=settings.telegram_bot_token,
            default_chat_id=settings.telegram_default_chat_id,
            timeout_seconds=settings.gateway_timeout_seconds,
        )
    )


def _parse_args(argv: list[str] | None) -> Namespace:
    parser = ArgumentParser(description="Notification worker runtime")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate startup configuration and exit",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="process at most one event cycle and exit",
    )
    parser.add_argument(
        "--max-idle-cycles",
        type=int,
        default=0,
        help="exit after N consecutive empty polls (0 = unlimited)",
    )
    return parser.parse_args(argv)


def _default_rabbitmq_http_fetch(
    api_base_url: str,
    username: str,
    password: str,
    queue_name: str,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    queue_ref = parse.quote(queue_name, safe="")
    url = f"{api_base_url}/queues/%2F/{queue_ref}/get"
    payload = json.dumps(
        {
            "count": 1,
            "ackmode": "ack_requeue_false",
            "encoding": "auto",
            "truncate": 50000,
        }
    ).encode("utf-8")
    auth_raw = f"{username}:{password}".encode("utf-8")
    auth_header = base64.b64encode(auth_raw).decode("utf-8")
    req = request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth_header}",
        },
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise NotificationSettingsError(f"RabbitMQ HTTP polling failed: {exc.code} {body}") from exc
    except OSError as exc:
        raise NotificationSettingsError(f"RabbitMQ HTTP polling failed: {exc}") from exc

    parsed = json.loads(raw) if raw else []
    if isinstance(parsed, list):
        rows = [row for row in parsed if isinstance(row, dict)]
        return [dict(row) for row in rows]
    return []


if __name__ == "__main__":
    raise SystemExit(main())
