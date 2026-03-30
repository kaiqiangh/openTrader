from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
import asyncio
from typing import Any, Protocol

from services.notification_service.models import (
    DeliveryResult,
    NotificationEvent,
    NotificationMessage,
)


class NotificationGateway(Protocol):
    name: str

    async def send(self, message: NotificationMessage) -> DeliveryResult: ...


@dataclass(slots=True)
class InMemoryGateway:
    name: str
    sent_messages: list[NotificationMessage] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.sent_messages.clear()

    async def send(self, message: NotificationMessage) -> DeliveryResult:
        self.sent_messages.append(message)
        return DeliveryResult(
            message_id=message.message_id,
            gateway=self.name,
            status="DELIVERED",
            attempt=1,
            detail=None,
        )


@dataclass(slots=True)
class GatewayDispatcher:
    gateways: Mapping[str, NotificationGateway]
    max_attempts: int = 3
    backoff_base_seconds: float = 0.2
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 2.0
    sleep_func: Callable[[float], Awaitable[None]] | None = None
    dlq_persist_func: Callable[[dict[str, Any]], Awaitable[None]] | None = None
    _dlq: list[dict[str, Any]] = field(default_factory=list, init=False)
    _sleep: Callable[[float], Awaitable[None]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if self.backoff_base_seconds < 0:
            raise ValueError("backoff_base_seconds must be non-negative")
        if self.backoff_multiplier < 1.0:
            raise ValueError("backoff_multiplier must be >= 1.0")
        if self.max_backoff_seconds <= 0:
            raise ValueError("max_backoff_seconds must be positive")
        self._dlq.clear()
        self._sleep = self.sleep_func or asyncio.sleep

    async def dispatch(
        self,
        *,
        event: NotificationEvent,
        messages: tuple[NotificationMessage, ...],
    ) -> tuple[DeliveryResult, ...]:
        results: list[DeliveryResult] = []
        for message in messages:
            gateway = self.gateways.get(message.gateway)
            if gateway is None:
                result = DeliveryResult(
                    message_id=message.message_id,
                    gateway=message.gateway,
                    status="FAILED",
                    attempt=0,
                    detail="gateway_not_registered",
                )
                self._append_dlq(event=event, message=message, result=result)
                results.append(result)
                continue

            result = await self._dispatch_single(gateway=gateway, event=event, message=message)
            results.append(result)
        return tuple(results)

    def dlq_items(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._dlq)

    async def _dispatch_single(
        self,
        *,
        gateway: NotificationGateway,
        event: NotificationEvent,
        message: NotificationMessage,
    ) -> DeliveryResult:
        last_error: str | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                gateway_result = await gateway.send(message)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc) or exc.__class__.__name__
                if not _is_retryable_exception(exc):
                    failed = DeliveryResult(
                        message_id=message.message_id,
                        gateway=gateway.name,
                        status="FAILED",
                        attempt=attempt,
                        detail=last_error,
                    )
                    self._append_dlq(event=event, message=message, result=failed)
                    return failed
                await self._sleep_after_attempt(attempt=attempt)
                continue

            if gateway_result.status == "DELIVERED":
                return DeliveryResult(
                    message_id=message.message_id,
                    gateway=gateway.name,
                    status="DELIVERED",
                    attempt=attempt,
                    detail=gateway_result.detail,
                )
            if _is_retryable_status(gateway_result.status):
                last_error = gateway_result.detail or "retryable_delivery_failed"
                await self._sleep_after_attempt(attempt=attempt)
                continue

            failed = DeliveryResult(
                message_id=message.message_id,
                gateway=gateway.name,
                status="FAILED",
                attempt=attempt,
                detail=gateway_result.detail or "terminal_delivery_failed",
            )
            self._append_dlq(event=event, message=message, result=failed)
            return failed

        failed = DeliveryResult(
            message_id=message.message_id,
            gateway=gateway.name,
            status="FAILED",
            attempt=self.max_attempts,
            detail=last_error or "delivery_failed",
        )
        self._append_dlq(event=event, message=message, result=failed)
        return failed

    def _append_dlq(
        self,
        *,
        event: NotificationEvent,
        message: NotificationMessage,
        result: DeliveryResult,
    ) -> None:
        item = {
            "event": event,
            "message": message,
            "result": result,
        }
        self._dlq.append(item)
        if self.dlq_persist_func is not None:
            asyncio.ensure_future(self.dlq_persist_func(item))

    async def _sleep_after_attempt(self, *, attempt: int) -> None:
        if attempt >= self.max_attempts:
            return
        delay = self.backoff_base_seconds * (self.backoff_multiplier ** max(0, attempt - 1))
        bounded_delay = min(delay, self.max_backoff_seconds)
        if bounded_delay <= 0:
            return
        await self._sleep(bounded_delay)


def _is_retryable_status(status: str) -> bool:
    normalized = status.strip().upper()
    return normalized in {"RETRYABLE", "RETRYABLE_ERROR", "FAILED_RETRYABLE"}


def _is_retryable_exception(exc: Exception) -> bool:
    retryable = getattr(exc, "retryable", True)
    return bool(retryable)
