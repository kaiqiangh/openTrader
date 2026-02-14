from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from services.notification_service.event_intake import NotificationEventIntake
from services.notification_service.gateway_dispatch import GatewayDispatcher, InMemoryGateway
from services.notification_service.models import NotificationPreference, NotificationSeverity
from services.notification_service.observability import NotificationObservabilityCollector
from services.notification_service.policy_router import NotificationPolicyRouter
from services.notification_service.publishers import NotificationEventBridge
from services.notification_service.service import NotificationService


class _CapturePublisher:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def publish(self, *, routing_key: str, message: dict[str, object]) -> None:
        self.messages.append({"routing_key": routing_key, "message": message})


def _source_strategy_envelope() -> dict[str, object]:
    return {
        "trace_id": str(uuid.uuid4()),
        "decision_id": str(uuid.uuid4()),
        "mode": "MOCK",
        "idempotency_key": f"agent.decision.intent_published:{uuid.uuid4()}",
        "event_type": "agent.decision.intent_published",
        "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "payload": {"strategy_id": "btc-momentum", "symbol": "BTC/USDT", "action": "BUY"},
        "service": "agent_orchestrator",
    }


@pytest.mark.asyncio
async def test_publish_bridge_to_notification_delivery_integration() -> None:
    capture = _CapturePublisher()
    bridge = NotificationEventBridge(publisher=capture)
    await bridge.publish_strategy_event(_source_strategy_envelope())

    assert len(capture.messages) == 1
    published = capture.messages[0]
    assert published["routing_key"] == "notify.events.raw"

    intake = NotificationEventIntake()
    router = NotificationPolicyRouter(
        preferences=(
            NotificationPreference(
                user_id="ops-1",
                min_severity=NotificationSeverity.INFO,
                gateways=("telegram",),
                event_types=("notify.strategy.event",),
            ),
        ),
        dedupe_window_seconds=60.0,
        rate_limit_per_minute=10,
    )
    gateway = InMemoryGateway(name="telegram")
    dispatcher = GatewayDispatcher(gateways={"telegram": gateway})
    observability = NotificationObservabilityCollector()
    service = NotificationService(
        intake=intake,
        policy_router=router,
        dispatcher=dispatcher,
        observability=observability,
    )
    result = await service.process_envelope(published["message"])  # type: ignore[arg-type]

    assert result.event.event_type == "notify.strategy.event"
    assert result.event.severity == NotificationSeverity.INFO
    assert len(result.messages) == 1
    assert result.results[0].status == "DELIVERED"
    assert result.messages[0].metadata["event_type"] == "notify.strategy.event"

    metrics = observability.snapshot()
    assert metrics["totals"]["received_total"] == 1
    assert metrics["totals"]["delivered_total"] == 1
    assert len(metrics["recent_logs"]) == 1
