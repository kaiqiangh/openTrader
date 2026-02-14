from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
import uuid

from services.notification_service.models import NotificationEvent, NotificationSeverity
from services.shared.contracts.message_envelope import validate_envelope


class NotificationEventIntake:
    """Normalizes source envelopes into notification events with severity classification."""

    def normalize(self, envelope: Mapping[str, Any]) -> NotificationEvent:
        validate_envelope(envelope)

        event_type = str(envelope["event_type"])
        payload_obj = envelope["payload"]
        payload = dict(payload_obj) if isinstance(payload_obj, Mapping) else {}

        severity = classify_severity(event_type=event_type, payload=payload)
        notification_event_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"notify:{envelope['idempotency_key']}:{event_type}:{severity.value}",
            )
        )

        return NotificationEvent(
            notification_event_id=notification_event_id,
            trace_id=str(envelope["trace_id"]),
            decision_id=str(envelope["decision_id"]),
            mode=str(envelope["mode"]),
            event_type=event_type,
            severity=severity,
            idempotency_key=str(envelope["idempotency_key"]),
            emitted_at=str(envelope["emitted_at"]),
            service=str(envelope.get("service", "unknown")),
            payload=payload,
        )


def classify_severity(*, event_type: str, payload: Mapping[str, Any]) -> NotificationSeverity:
    lowered = event_type.lower()

    if lowered.startswith("risk."):
        if "kill_switch" in lowered or "tripped" in lowered:
            return NotificationSeverity.CRITICAL
        return NotificationSeverity.WARNING

    if lowered.startswith("notify.risk."):
        declared = _declared_severity(payload)
        if declared is not None:
            return declared
        if "kill_switch" in lowered or "tripped" in lowered:
            return NotificationSeverity.CRITICAL
        return NotificationSeverity.WARNING

    if lowered.startswith("system.") or lowered.startswith("notify.system."):
        return NotificationSeverity.CRITICAL

    if lowered.startswith("oms.order."):
        if any(token in lowered for token in ("rejected", "cancel", "expired")):
            return NotificationSeverity.WARNING
        return NotificationSeverity.INFO

    if lowered.startswith("agent.decision"):
        if "rejected" in lowered:
            return NotificationSeverity.WARNING
        return NotificationSeverity.INFO

    declared = _declared_severity(payload)
    if declared is not None:
        return declared

    return NotificationSeverity.INFO


def _declared_severity(payload: Mapping[str, Any]) -> NotificationSeverity | None:
    declared = payload.get("severity")
    if isinstance(declared, str):
        normalized = declared.strip().upper()
        if normalized in {"INFO", "WARNING", "CRITICAL"}:
            return NotificationSeverity(normalized)
    return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_hash(*, values: str) -> str:
    joined = "|".join(values)
    return sha256(joined.encode("utf-8")).hexdigest()
