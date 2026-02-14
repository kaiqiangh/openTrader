from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from services.notification_service.event_intake import NotificationEventIntake
from services.notification_service.gateway_dispatch import GatewayDispatcher, InMemoryGateway
from services.notification_service.models import DeliveryResult, NotificationPreference, NotificationSeverity
from services.notification_service.policy_router import NotificationPolicyRouter
from services.notification_service.service import NotificationService


class _TerminalGatewayError(RuntimeError):
    retryable = False


class _TerminalExceptionGateway(InMemoryGateway):
    async def send(self, message):  # type: ignore[override]
        raise _TerminalGatewayError("telegram_invalid_chat")


class _RetryableAlwaysFailGateway(InMemoryGateway):
    async def send(self, message):  # type: ignore[override]
        return DeliveryResult(
            message_id=message.message_id,
            gateway=self.name,
            status="RETRYABLE_ERROR",
            attempt=1,
            detail="http_503",
        )


def _envelope(*, event_type: str, mode: str = "MOCK") -> dict[str, object]:
    return {
        "trace_id": str(uuid.uuid4()),
        "decision_id": str(uuid.uuid4()),
        "mode": mode,
        "idempotency_key": f"event:{event_type}:{uuid.uuid4()}",
        "event_type": event_type,
        "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "payload": {"strategy_id": "btc-momentum", "symbol": "BTC/USDT", "reason": "test"},
        "service": "tests",
    }


def _service_with_gateway(
    gateway: InMemoryGateway,
    *,
    sleep_func=None,
    max_attempts: int = 3,
    backoff_base_seconds: float = 0.1,
    backoff_multiplier: float = 2.0,
    max_backoff_seconds: float = 0.5,
    gateway_name: str = "telegram",
) -> tuple[NotificationService, GatewayDispatcher]:
    intake = NotificationEventIntake()
    router = NotificationPolicyRouter(
        preferences=(
            NotificationPreference(
                user_id="ops-1",
                min_severity=NotificationSeverity.INFO,
                gateways=(gateway_name,),
            ),
        ),
        dedupe_window_seconds=60.0,
        rate_limit_per_minute=10,
    )
    dispatcher = GatewayDispatcher(
        gateways={gateway.name: gateway},
        max_attempts=max_attempts,
        backoff_base_seconds=backoff_base_seconds,
        backoff_multiplier=backoff_multiplier,
        max_backoff_seconds=max_backoff_seconds,
        sleep_func=sleep_func,
    )
    service = NotificationService(intake=intake, policy_router=router, dispatcher=dispatcher)
    return service, dispatcher


@pytest.mark.asyncio
async def test_terminal_exception_is_not_retried_and_goes_to_dlq() -> None:
    delays: list[float] = []

    async def _sleep(delay_seconds: float) -> None:
        delays.append(delay_seconds)

    service, dispatcher = _service_with_gateway(
        _TerminalExceptionGateway(name="telegram"),
        sleep_func=_sleep,
        max_attempts=4,
    )
    result = await service.process_envelope(_envelope(event_type="notify.risk.event"))

    assert len(result.results) == 1
    assert result.results[0].status == "FAILED"
    assert result.results[0].attempt == 1
    assert len(delays) == 0
    assert len(dispatcher.dlq_items()) == 1


@pytest.mark.asyncio
async def test_retryable_failures_exhaust_attempts_with_bounded_backoff() -> None:
    delays: list[float] = []

    async def _sleep(delay_seconds: float) -> None:
        delays.append(delay_seconds)

    service, dispatcher = _service_with_gateway(
        _RetryableAlwaysFailGateway(name="telegram"),
        sleep_func=_sleep,
        max_attempts=3,
        backoff_base_seconds=0.1,
        backoff_multiplier=3.0,
        max_backoff_seconds=0.2,
    )
    result = await service.process_envelope(_envelope(event_type="notify.system.event"))

    assert len(result.results) == 1
    assert result.results[0].status == "FAILED"
    assert result.results[0].attempt == 3
    assert delays == [0.1, 0.2]
    assert len(dispatcher.dlq_items()) == 1


@pytest.mark.asyncio
async def test_unregistered_gateway_message_moves_to_dlq() -> None:
    service, dispatcher = _service_with_gateway(
        InMemoryGateway(name="telegram"),
        gateway_name="webhook",
    )
    result = await service.process_envelope(_envelope(event_type="notify.strategy.event"))

    assert len(result.results) == 1
    assert result.results[0].status == "FAILED"
    assert result.results[0].attempt == 0
    assert result.results[0].detail == "gateway_not_registered"
    assert len(dispatcher.dlq_items()) == 1
