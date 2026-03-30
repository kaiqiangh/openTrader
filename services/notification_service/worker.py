from __future__ import annotations

from argparse import ArgumentParser, Namespace
from asyncio import run as asyncio_run
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol
from urllib import parse
import httpx
import asyncio
import logging
import base64
import json

from services.notification_service.event_intake import NotificationEventIntake
from services.notification_service.gateway_dispatch import GatewayDispatcher, InMemoryGateway
from services.notification_service.models import (
    NotificationPreference,
    NotificationProcessingResult,
)
from services.notification_service.observability import (
    NotificationObservabilityCollector,
    utc_now_iso,
)
from services.notification_service.policy_router import NotificationPolicyRouter
from services.notification_service.service import NotificationService
from services.notification_service.settings import (
    NotificationSettingsError,
    NotificationWorkerSettings,
    load_notification_worker_settings,
)
from services.shared.runtime.broker import InMemoryTopicBroker
from services.shared.runtime.prometheus import PrometheusRegistry
from services.shared.runtime.structured_logging import StructuredLogger

_WORKER_SERVICE_NAME = "notification_worker"
_WORKER_POLLS_METRIC = "open_trader_notification_worker_polls_total"
_WORKER_LATENCY_METRIC = "open_trader_notification_worker_process_duration_seconds"
_WORKER_DELIVERY_METRIC = "open_trader_notification_delivery_results_total"


class NotificationEnvelopeConsumer(Protocol):
    async def consume(
        self, *, queue_name: str, timeout_seconds: float
    ) -> Mapping[str, Any] | None: ...


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
RabbitMQHTTPDeclareQueueFn = Callable[[str, str, str, str, float], None]


class RabbitMQHTTPPollingError(NotificationSettingsError):
    def __init__(self, *, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"RabbitMQ HTTP polling failed: {status_code} {body}")


class RabbitMQHTTPConsumer:
    def __init__(
        self,
        *,
        api_base_url: str,
        username: str,
        password: str,
        request_timeout_seconds: float,
        fetch_fn: RabbitMQHTTPFetchFn | None = None,
        declare_queue_fn: RabbitMQHTTPDeclareQueueFn | None = None,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.username = username
        self.password = password
        self.request_timeout_seconds = request_timeout_seconds
        self._fetch_fn = fetch_fn or _default_rabbitmq_http_fetch
        self._declare_queue_fn = declare_queue_fn or _default_rabbitmq_http_declare_queue
        self._declared_queues: set[str] = set()

    async def consume(self, *, queue_name: str, timeout_seconds: float) -> Mapping[str, Any] | None:
        _ = timeout_seconds
        try:
            rows = await asyncio.to_thread(
                self._fetch_fn,
                self.api_base_url,
                self.username,
                self.password,
                queue_name,
                self.request_timeout_seconds,
            )
        except RabbitMQHTTPPollingError as exc:
            if exc.status_code == 404 and "queue_not_found" in exc.body:
                await self._declare_queue(queue_name)
                return None
            raise
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

    async def _declare_queue(self, queue_name: str) -> None:
        if queue_name in self._declared_queues:
            return
        await asyncio.to_thread(
            self._declare_queue_fn,
            self.api_base_url,
            self.username,
            self.password,
            queue_name,
            self.request_timeout_seconds,
        )
        self._declared_queues.add(queue_name)


@dataclass(slots=True)
class NotificationWorker:
    consumer: NotificationEnvelopeConsumer
    service: NotificationService
    queue_name: str
    poll_timeout_seconds: float
    logger: StructuredLogger | None = None
    metrics: PrometheusRegistry | None = None

    async def run_once(self) -> NotificationProcessingResult | None:
        started = perf_counter()
        envelope = await self.consumer.consume(
            queue_name=self.queue_name,
            timeout_seconds=self.poll_timeout_seconds,
        )
        if envelope is None:
            self._record_poll_result(result="empty")
            return None

        trace_id = str(envelope.get("trace_id", "unknown"))
        decision_id = str(envelope.get("decision_id", "unknown"))
        mode = str(envelope.get("mode", "UNKNOWN"))
        event_type = str(envelope.get("event_type", "unknown"))

        if self.logger is not None:
            self.logger.info(
                event="notification.worker.envelope.received",
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                context={"queue_name": self.queue_name, "event_type": event_type},
            )

        try:
            result = await self.service.process_envelope(envelope)
        except Exception as exc:
            latency = max(0.0, perf_counter() - started)
            self._record_latency(latency)
            self._record_poll_result(result="failed")
            if self.logger is not None:
                self.logger.error(
                    event="notification.worker.envelope.failed",
                    trace_id=trace_id,
                    decision_id=decision_id,
                    mode=mode,
                    context={
                        "queue_name": self.queue_name,
                        "event_type": event_type,
                        "error_type": type(exc).__name__,
                    },
                )
            raise

        latency = max(0.0, perf_counter() - started)
        self._record_latency(latency)
        self._record_poll_result(result="processed")
        self._record_delivery_results(result=result)
        if self.logger is not None:
            self.logger.info(
                event="notification.worker.envelope.processed",
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                context={
                    "queue_name": self.queue_name,
                    "event_type": result.event.event_type,
                    "severity": result.event.severity.value,
                    "messages_count": len(result.messages),
                    "delivery_results_count": len(result.results),
                    "latency_ms": latency * 1000.0,
                },
            )
        return result

    def render_metrics(self) -> str:
        if self.metrics is None:
            return ""
        return self.metrics.render()

    def _record_poll_result(self, *, result: str) -> None:
        if self.metrics is None:
            return
        self.metrics.inc_counter(
            name=_WORKER_POLLS_METRIC,
            help_text="Notification worker poll outcomes",
            label_values={"service": _WORKER_SERVICE_NAME, "result": result},
        )

    def _record_latency(self, latency_seconds: float) -> None:
        if self.metrics is None:
            return
        self.metrics.observe_histogram(
            name=_WORKER_LATENCY_METRIC,
            help_text="Notification worker envelope processing latency seconds",
            value=max(0.0, float(latency_seconds)),
            label_values={"service": _WORKER_SERVICE_NAME, "queue": self.queue_name},
        )

    def _record_delivery_results(self, *, result: NotificationProcessingResult) -> None:
        if self.metrics is None:
            return
        for delivery in result.results:
            self.metrics.inc_counter(
                name=_WORKER_DELIVERY_METRIC,
                help_text="Notification delivery result counts by status and gateway",
                label_values={
                    "service": _WORKER_SERVICE_NAME,
                    "gateway": delivery.gateway,
                    "status": delivery.status,
                },
            )


def _build_persist_fn() -> Callable[[NotificationProcessingResult], None] | None:
    """Build a persistence callback that writes notification results to the database.

    Returns None if the database is not available (graceful degradation).
    """
    try:
        from services.api.repositories import ControlPlaneRepository
        from services.api.state import NotificationDeliveryRecord

        repo = ControlPlaneRepository.from_env()
    except Exception:
        return None

    def _persist(result: NotificationProcessingResult) -> None:
        event = result.event
        now = utc_now_iso()

        # Persist the notification event
        try:
            repo.persist_notification_event(
                notification_event_id=event.notification_event_id,
                trace_id=event.trace_id,
                decision_id=event.decision_id,
                event_type=event.event_type,
                severity=event.severity.value,
                title=event.event_type,
                body=json.dumps(event.payload, ensure_ascii=False, default=str),
                payload_json=json.dumps(event.payload, ensure_ascii=False, default=str),
                idempotency_key=event.idempotency_key,
                emitted_at=event.emitted_at,
            )
        except Exception:
            pass

        # Persist delivery results
        for delivery in result.results:
            try:
                repo.persist_notification_delivery(
                    NotificationDeliveryRecord(
                        notification_event_id=event.notification_event_id,
                        trace_id=event.trace_id,
                        decision_id=event.decision_id,
                        event_type=event.event_type,
                        severity=event.severity.value,
                        gateway=delivery.gateway,
                        delivery_status=delivery.status,
                        attempt=delivery.attempt,
                        detail=delivery.detail,
                        logged_at=now,
                    )
                )
            except Exception:
                pass

        # Persist DLQ entries for failed deliveries
        for delivery in result.results:
            if delivery.status.strip().upper() not in {"DELIVERED"}:
                try:
                    repo.persist_notification_dlq_entry(
                        notification_event_id=event.notification_event_id,
                        gateway=delivery.gateway,
                        failure_reason=delivery.detail or "delivery_failed",
                        failed_attempts=delivery.attempt,
                        last_error=delivery.detail,
                        moved_at=now,
                    )
                except Exception:
                    pass

    return _persist


def build_notification_worker_from_settings(
    *,
    settings: NotificationWorkerSettings,
    topology_path: str = "config/rabbitmq/topology.json",
) -> NotificationWorker:
    logger = StructuredLogger(service=_WORKER_SERVICE_NAME)
    metrics = PrometheusRegistry()
    gateways = {
        settings.default_gateway: _build_gateway(settings=settings),
    }
    persist_fn = _build_persist_fn()
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
        persist_fn=persist_fn,
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
        logger=logger,
        metrics=metrics,
    )


async def run_worker_loop(
    *,
    settings: NotificationWorkerSettings,
    once: bool = False,
    max_idle_cycles: int = 0,
) -> int:
    startup_logger = StructuredLogger(service=_WORKER_SERVICE_NAME)
    if not settings.enabled:
        startup_logger.info(
            event="notification.worker.disabled", context={"reason": "NOTIFY_ENABLED=false"}
        )
        return 0

    worker = build_notification_worker_from_settings(settings=settings)
    idle_cycles = 0
    while True:
        try:
            result = await worker.run_once()
        except Exception:
            logging.getLogger(__name__).error("notification_worker_error", exc_info=True)
            await asyncio.sleep(1.0)
            continue
        if result is None:
            idle_cycles += 1
            if once:
                return 0
            if max_idle_cycles > 0 and idle_cycles >= max_idle_cycles:
                return 0
            await asyncio.sleep(settings.idle_sleep_seconds)
            continue

        idle_cycles = 0
        if once:
            return 0


def main(argv: list[str] | None = None) -> int:
    startup_logger = StructuredLogger(service=_WORKER_SERVICE_NAME)
    args = _parse_args(argv)
    try:
        settings = load_notification_worker_settings()
    except NotificationSettingsError as exc:
        startup_logger.error(
            event="notification.worker.startup.validation_failed",
            context={"error": str(exc)},
        )
        return 1

    if args.validate_only:
        startup_logger.info(event="notification.worker.startup.validation_passed")
        return 0

    return asyncio_run(
        run_worker_loop(
            settings=settings,
            once=args.once,
            max_idle_cycles=args.max_idle_cycles,
        )
    )


def _build_gateway(*, settings: NotificationWorkerSettings) -> Any:
    if settings.default_gateway == "telegram":
        if not settings.telegram_bot_token or not settings.telegram_default_chat_id:
            raise NotificationSettingsError(
                "telegram gateway enabled but telegram secrets are missing"
            )
        from services.notification_service.telegram_gateway import (
            TelegramGateway,
            TelegramGatewayConfig,
        )

        return TelegramGateway(
            config=TelegramGatewayConfig(
                bot_token=settings.telegram_bot_token,
                default_chat_id=settings.telegram_default_chat_id,
                timeout_seconds=settings.gateway_timeout_seconds,
            )
        )

    if settings.default_gateway == "email":
        from services.notification_service.email_gateway import load_email_gateway_from_env

        gateway = load_email_gateway_from_env()
        if gateway is None:
            raise NotificationSettingsError("email gateway enabled but SMTP settings are missing")
        return gateway

    if settings.default_gateway == "webhook":
        import os

        webhook_url = os.getenv("WEBHOOK_URL", "").strip()
        if not webhook_url:
            raise NotificationSettingsError("webhook gateway enabled but WEBHOOK_URL is missing")
        from services.notification_service.webhook_gateway import (
            WebhookGateway,
            WebhookGatewayConfig,
        )

        webhook_secret = os.getenv("WEBHOOK_SECRET", "").strip()
        return WebhookGateway(
            config=WebhookGatewayConfig(
                url=webhook_url,
                timeout_seconds=settings.gateway_timeout_seconds,
                secret=webhook_secret,
            )
        )

    # inmemory and unknown gateways fall back to in-memory test gateway
    return InMemoryGateway(name=settings.default_gateway)


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
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {auth_header}",
    }
    try:
        with httpx.Client(timeout=timeout_seconds, verify=True) as client:
            response = client.post(url, content=payload, headers=headers)
            response.raise_for_status()
            raw = response.text
    except httpx.HTTPStatusError as exc:
        body = exc.response.text
        raise RabbitMQHTTPPollingError(
            status_code=int(exc.response.status_code), body=body
        ) from exc
    except httpx.HTTPError as exc:
        raise NotificationSettingsError(f"RabbitMQ HTTP polling failed: {exc}") from exc

    parsed = json.loads(raw) if raw else []
    if isinstance(parsed, list):
        rows = [row for row in parsed if isinstance(row, dict)]
        return [dict(row) for row in rows]
    return []


def _default_rabbitmq_http_declare_queue(
    api_base_url: str,
    username: str,
    password: str,
    queue_name: str,
    timeout_seconds: float,
) -> None:
    queue_ref = parse.quote(queue_name, safe="")
    url = f"{api_base_url}/queues/%2F/{queue_ref}"
    payload = json.dumps(
        {
            "durable": True,
            "auto_delete": False,
            "arguments": {},
        }
    ).encode("utf-8")
    auth_raw = f"{username}:{password}".encode("utf-8")
    auth_header = base64.b64encode(auth_raw).decode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {auth_header}",
    }
    try:
        with httpx.Client(timeout=timeout_seconds, verify=True) as client:
            response = client.put(url, content=payload, headers=headers)
            response.raise_for_status()
            return
    except httpx.HTTPStatusError as exc:
        body = exc.response.text
        raise NotificationSettingsError(
            f"RabbitMQ queue declare failed: {exc.response.status_code} {body}"
        ) from exc
    except httpx.HTTPError as exc:
        raise NotificationSettingsError(f"RabbitMQ queue declare failed: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
