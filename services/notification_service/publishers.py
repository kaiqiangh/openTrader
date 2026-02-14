from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Protocol
import uuid

from services.notification_service.event_intake import classify_severity
from services.shared.contracts.message_envelope import validate_envelope


class NotificationEventPublisher(Protocol):
    async def publish(self, *, routing_key: str, message: dict[str, Any]) -> Any: ...


class NotificationEventBridge:
    """Normalizes source pipeline events into notification-source envelopes."""

    def __init__(
        self,
        *,
        publisher: NotificationEventPublisher,
        routing_key: str = "notify.events.raw",
        service_name: str = "notification_bridge",
    ) -> None:
        self.publisher = publisher
        self.routing_key = routing_key
        self.service_name = service_name

    async def publish_strategy_event(self, source_envelope: Mapping[str, Any]) -> dict[str, Any]:
        return await self._publish_from_source(
            source_envelope=source_envelope,
            notification_event_type="notify.strategy.event",
        )

    async def publish_oms_event(self, source_envelope: Mapping[str, Any]) -> dict[str, Any]:
        return await self._publish_from_source(
            source_envelope=source_envelope,
            notification_event_type="notify.oms.event",
        )

    async def publish_risk_event(self, source_envelope: Mapping[str, Any]) -> dict[str, Any]:
        return await self._publish_from_source(
            source_envelope=source_envelope,
            notification_event_type="notify.risk.event",
        )

    async def publish_system_health_event(
        self,
        *,
        trace_id: str,
        mode: str,
        event_type: str,
        severity: str,
        reason: str,
        details: Mapping[str, Any],
    ) -> dict[str, Any]:
        decision_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"system:{event_type}:{reason}"))
        source = {
            "trace_id": _safe_uuid(trace_id, prefix="trace"),
            "decision_id": decision_id,
            "mode": mode,
            "idempotency_key": f"system:{event_type}:{reason}",
            "event_type": event_type,
            "emitted_at": _utc_now_iso(),
            "payload": {
                "reason": reason,
                "details": dict(details),
                "severity": severity,
            },
            "service": "system_health",
        }
        return await self._publish_from_source(
            source_envelope=source,
            notification_event_type="notify.system.event",
        )

    async def _publish_from_source(
        self,
        *,
        source_envelope: Mapping[str, Any],
        notification_event_type: str,
    ) -> dict[str, Any]:
        trace_id = _safe_uuid(str(source_envelope.get("trace_id", "")), prefix="trace")
        decision_id = _safe_uuid(str(source_envelope.get("decision_id", "")), prefix="decision")
        mode = str(source_envelope.get("mode", "REAL")).strip().upper() or "REAL"
        idempotency_key = str(source_envelope.get("idempotency_key", "")) or str(uuid.uuid4())
        source_event_type = str(source_envelope.get("event_type", "unknown"))

        payload_obj = source_envelope.get("payload")
        payload = dict(payload_obj) if isinstance(payload_obj, Mapping) else {}
        severity = classify_severity(event_type=source_event_type, payload=payload).value

        notification_envelope = {
            "trace_id": trace_id,
            "decision_id": decision_id,
            "mode": mode if mode in {"MOCK", "REAL"} else "REAL",
            "idempotency_key": f"notify:{notification_event_type}:{idempotency_key}",
            "event_type": notification_event_type,
            "severity": severity,
            "emitted_at": str(source_envelope.get("emitted_at", _utc_now_iso())),
            "payload": {
                "source_event_type": source_event_type,
                "source_service": str(source_envelope.get("service", "unknown")),
                "source_payload": payload,
                "severity": severity,
            },
            "service": self.service_name,
        }
        validate_envelope(notification_envelope)
        await self.publisher.publish(routing_key=self.routing_key, message=notification_envelope)
        return notification_envelope


def _safe_uuid(value: str, *, prefix: str) -> str:
    try:
        uuid.UUID(value)
        return value
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{prefix}:{value}"))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
