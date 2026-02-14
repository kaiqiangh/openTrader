from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping
import uuid


class EnvelopeValidationError(ValueError):
    """Raised when a message envelope does not satisfy the canonical contract."""


REQUIRED_FIELDS = {
    "trace_id",
    "decision_id",
    "mode",
    "idempotency_key",
    "event_type",
    "emitted_at",
    "payload",
}
ALLOWED_MODES = {"MOCK", "REAL"}


def _validate_uuid(value: Any, field_name: str) -> None:
    if not isinstance(value, str):
        raise EnvelopeValidationError(f"{field_name} must be a UUID string")
    try:
        uuid.UUID(value)
    except ValueError as exc:  # pragma: no cover - explicit error path
        raise EnvelopeValidationError(f"{field_name} must be a valid UUID") from exc


def _validate_iso_datetime(value: Any, field_name: str) -> None:
    if not isinstance(value, str):
        raise EnvelopeValidationError(f"{field_name} must be an ISO-8601 string")
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:  # pragma: no cover - explicit error path
        raise EnvelopeValidationError(f"{field_name} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise EnvelopeValidationError(f"{field_name} must include timezone information")


def validate_envelope(envelope: Mapping[str, Any]) -> None:
    if not isinstance(envelope, Mapping):
        raise EnvelopeValidationError("Envelope must be a mapping")

    missing_fields = REQUIRED_FIELDS - set(envelope.keys())
    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise EnvelopeValidationError(f"Missing required field(s): {missing}")

    _validate_uuid(envelope["trace_id"], "trace_id")
    _validate_uuid(envelope["decision_id"], "decision_id")

    mode = envelope["mode"]
    if mode not in ALLOWED_MODES:
        raise EnvelopeValidationError("mode must be one of: MOCK, REAL")

    idempotency_key = envelope["idempotency_key"]
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise EnvelopeValidationError("idempotency_key must be a non-empty string")

    event_type = envelope["event_type"]
    if not isinstance(event_type, str) or not event_type.strip():
        raise EnvelopeValidationError("event_type must be a non-empty string")

    _validate_iso_datetime(envelope["emitted_at"], "emitted_at")

    payload = envelope["payload"]
    if not isinstance(payload, Mapping):
        raise EnvelopeValidationError("payload must be an object")
