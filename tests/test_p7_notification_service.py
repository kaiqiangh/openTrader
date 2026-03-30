from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from services.notification_service.event_intake import NotificationEventIntake
from services.notification_service.gateway_dispatch import GatewayDispatcher, InMemoryGateway
from services.notification_service.models import (
    DeliveryResult,
    NotificationPreference,
    NotificationSeverity,
)
from services.notification_service.policy_router import NotificationPolicyRouter
from services.notification_service.service import NotificationService


class _AlwaysFailGateway(InMemoryGateway):
    async def send(self, message):  # type: ignore[override]
        raise RuntimeError("gateway_unavailable")


class _RetryThenDeliverGateway(InMemoryGateway):
    def __init__(self, *, name: str, retryable_failures: int) -> None:
        super().__init__(name=name)
        self.retryable_failures = retryable_failures
        self.attempts = 0

    async def send(self, message):  # type: ignore[override]
        self.attempts += 1
        if self.attempts <= self.retryable_failures:
            return DeliveryResult(
                message_id=message.message_id,
                gateway=self.name,
                status="RETRYABLE_ERROR",
                attempt=self.attempts,
                detail="http_503",
            )
        return await super().send(message)


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


@pytest.mark.asyncio
async def test_notification_service_routes_and_dispatches_message() -> None:
    intake = NotificationEventIntake()
    router = NotificationPolicyRouter(
        preferences=(
            NotificationPreference(
                user_id="ops-1",
                min_severity=NotificationSeverity.INFO,
                gateways=("telegram",),
            ),
        ),
        dedupe_window_seconds=60.0,
        rate_limit_per_minute=10,
    )
    gateway = InMemoryGateway(name="telegram")
    dispatcher = GatewayDispatcher(gateways={"telegram": gateway})
    service = NotificationService(intake=intake, policy_router=router, dispatcher=dispatcher)

    result = await service.process_envelope(_envelope(event_type="agent.decision.intent_published"))

    assert result.event.severity == NotificationSeverity.INFO
    assert len(result.messages) == 1
    assert len(result.results) == 1
    assert result.results[0].status == "DELIVERED"


@pytest.mark.asyncio
async def test_notification_policy_router_dedupe_and_rate_limit() -> None:
    intake = NotificationEventIntake()
    router = NotificationPolicyRouter(
        preferences=(
            NotificationPreference(
                user_id="ops-1",
                min_severity=NotificationSeverity.INFO,
                gateways=("telegram",),
            ),
        ),
        dedupe_window_seconds=120.0,
        rate_limit_per_minute=1,
    )

    event = intake.normalize(_envelope(event_type="oms.order.filled"))
    first = router.route(event=event, now_seconds=1000.0)
    second = router.route(event=event, now_seconds=1001.0)

    assert len(first) == 1
    assert second == ()
    counters = router.suppression_counts()
    assert counters["dedupe"] == 1
    assert counters["rate_limit"] == 0


@pytest.mark.asyncio
async def test_notification_dispatcher_moves_failures_to_dlq() -> None:
    intake = NotificationEventIntake()
    router = NotificationPolicyRouter(
        preferences=(
            NotificationPreference(
                user_id="ops-1",
                min_severity=NotificationSeverity.WARNING,
                gateways=("telegram",),
            ),
        ),
        dedupe_window_seconds=60.0,
        rate_limit_per_minute=10,
    )
    dispatcher = GatewayDispatcher(
        gateways={"telegram": _AlwaysFailGateway(name="telegram")}, max_attempts=2
    )
    service = NotificationService(intake=intake, policy_router=router, dispatcher=dispatcher)

    result = await service.process_envelope(
        _envelope(event_type="risk.control.risk.kill_switch.enabled")
    )

    assert result.event.severity == NotificationSeverity.CRITICAL
    assert len(result.results) == 1
    assert result.results[0].status == "FAILED"
    assert len(dispatcher.dlq_items()) == 1


@pytest.mark.asyncio
async def test_notification_dispatcher_retries_with_backoff_and_eventually_delivers() -> None:
    intake = NotificationEventIntake()
    router = NotificationPolicyRouter(
        preferences=(
            NotificationPreference(
                user_id="ops-1",
                min_severity=NotificationSeverity.INFO,
                gateways=("telegram",),
            ),
        ),
        dedupe_window_seconds=60.0,
        rate_limit_per_minute=10,
    )
    gateway = _RetryThenDeliverGateway(name="telegram", retryable_failures=2)
    delays: list[float] = []

    async def _sleep(delay_seconds: float) -> None:
        delays.append(delay_seconds)

    dispatcher = GatewayDispatcher(
        gateways={"telegram": gateway},
        max_attempts=3,
        backoff_base_seconds=0.2,
        backoff_multiplier=2.0,
        max_backoff_seconds=2.0,
        sleep_func=_sleep,
    )
    service = NotificationService(intake=intake, policy_router=router, dispatcher=dispatcher)

    result = await service.process_envelope(_envelope(event_type="oms.order.filled"))

    assert len(result.results) == 1
    assert result.results[0].status == "DELIVERED"
    assert result.results[0].attempt == 3
    assert delays == [0.2, 0.4]
