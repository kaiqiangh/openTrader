from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from services.notification_service.models import DeliveryResult, NotificationEvent, NotificationMessage


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
    _dlq: list[dict[str, Any]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        self._dlq.clear()

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
                last_error = str(exc)
                continue

            if gateway_result.status == "DELIVERED":
                return DeliveryResult(
                    message_id=message.message_id,
                    gateway=gateway.name,
                    status="DELIVERED",
                    attempt=attempt,
                    detail=gateway_result.detail,
                )
            last_error = gateway_result.detail or "delivery_failed"

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
        self._dlq.append(
            {
                "event": event,
                "message": message,
                "result": result,
            }
        )
