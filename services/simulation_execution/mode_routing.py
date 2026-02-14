from __future__ import annotations

from typing import Any, Mapping

from services.shared.contracts.message_envelope import validate_envelope

MOCK_ROUTING_KEY = "execution.intent.mock"
REAL_ROUTING_KEY = "execution.intent.real"


class ModeRoutingError(ValueError):
    """Raised when intent routing or mode isolation checks fail."""


def routing_key_for_mode(mode: str) -> str:
    normalized = mode.upper()
    if normalized == "MOCK":
        return MOCK_ROUTING_KEY
    if normalized == "REAL":
        return REAL_ROUTING_KEY
    raise ModeRoutingError(f"Unsupported execution mode: {mode}")


def route_execution_intent(envelope: Mapping[str, Any]) -> str:
    validate_envelope(envelope)
    event_type = str(envelope.get("event_type", ""))
    if event_type != "execution.intent.created":
        raise ModeRoutingError(
            f"Unexpected event_type for routing policy: {event_type}; expected execution.intent.created"
        )
    return routing_key_for_mode(str(envelope["mode"]))


def assert_no_mode_leakage(*, routing_key: str, envelope: Mapping[str, Any]) -> None:
    expected = route_execution_intent(envelope)
    if routing_key != expected:
        raise ModeRoutingError(
            f"Mode leakage detected: envelope mode {envelope['mode']} must route to {expected}, got {routing_key}"
        )
