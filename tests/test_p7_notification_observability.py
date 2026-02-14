from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from services.notification_service.event_intake import NotificationEventIntake
from services.notification_service.gateway_dispatch import GatewayDispatcher, InMemoryGateway
from services.notification_service.models import NotificationPreference, NotificationSeverity
from services.notification_service.observability import NotificationObservabilityCollector
from services.notification_service.policy_router import NotificationPolicyRouter
from services.notification_service.service import NotificationService


def _envelope(*, event_type: str, mode: str = "MOCK", suffix: str = "a") -> dict[str, object]:
    return {
        "trace_id": str(uuid.uuid4()),
        "decision_id": str(uuid.uuid4()),
        "mode": mode,
        "idempotency_key": f"event:{event_type}:{suffix}",
        "event_type": event_type,
        "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "payload": {"strategy_id": "btc-momentum", "symbol": "BTC/USDT", "reason": "test"},
        "service": "tests",
    }


@pytest.mark.asyncio
async def test_notification_observability_records_metrics_logs_and_spans() -> None:
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
    dispatcher = GatewayDispatcher(gateways={"telegram": InMemoryGateway(name="telegram")})
    observability = NotificationObservabilityCollector()
    service = NotificationService(
        intake=intake,
        policy_router=router,
        dispatcher=dispatcher,
        observability=observability,
    )

    await service.process_envelope(_envelope(event_type="oms.order.filled"))
    snapshot = observability.snapshot()

    assert snapshot["totals"]["received_total"] == 1
    assert snapshot["totals"]["dispatched_total"] == 1
    assert snapshot["totals"]["delivered_total"] == 1
    assert snapshot["totals"]["failed_total"] == 0

    recent_logs = snapshot["recent_logs"]
    assert len(recent_logs) == 1
    assert recent_logs[0]["gateway"] == "telegram"
    assert recent_logs[0]["delivery_status"] == "DELIVERED"
    assert recent_logs[0]["trace_id"]

    spans = snapshot["recent_spans"]
    assert len(spans) >= 2
    assert {span["stage"] for span in spans}.issuperset({"policy_router", "gateway_dispatch"})


@pytest.mark.asyncio
async def test_notification_observability_tracks_filtered_events_from_dedupe() -> None:
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
        rate_limit_per_minute=10,
    )
    dispatcher = GatewayDispatcher(gateways={"telegram": InMemoryGateway(name="telegram")})
    observability = NotificationObservabilityCollector()
    service = NotificationService(
        intake=intake,
        policy_router=router,
        dispatcher=dispatcher,
        observability=observability,
    )

    envelope = _envelope(event_type="oms.order.filled", suffix="same")
    await service.process_envelope(envelope, now_seconds=1000.0)
    await service.process_envelope(envelope, now_seconds=1001.0)
    snapshot = observability.snapshot()

    assert snapshot["totals"]["received_total"] == 2
    assert snapshot["totals"]["filtered_total"] >= 1
    assert snapshot["suppression"]["dedupe"] >= 1
