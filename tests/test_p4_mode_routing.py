from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from services.simulation_execution.mode_routing import (
    MOCK_ROUTING_KEY,
    REAL_ROUTING_KEY,
    ModeRoutingError,
    assert_no_mode_leakage,
    route_execution_intent,
)


def _intent_envelope(*, mode: str) -> dict[str, object]:
    return {
        "trace_id": str(uuid.uuid4()),
        "decision_id": str(uuid.uuid4()),
        "mode": mode,
        "idempotency_key": f"execution.intent:{mode.lower()}:{uuid.uuid4()}",
        "event_type": "execution.intent.created",
        "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "payload": {
            "strategy_id": "scalp-long-short",
            "symbol": "BTC/USDT",
            "action": "BUY",
            "quantity": 0.2,
            "market_context": {"mid_price": 42000.0},
        },
    }


def test_route_execution_intent_to_mode_specific_queue() -> None:
    assert route_execution_intent(_intent_envelope(mode="MOCK")) == MOCK_ROUTING_KEY
    assert route_execution_intent(_intent_envelope(mode="REAL")) == REAL_ROUTING_KEY


def test_assert_no_mode_leakage_raises_for_mismatch() -> None:
    with pytest.raises(ModeRoutingError):
        assert_no_mode_leakage(
            routing_key=REAL_ROUTING_KEY,
            envelope=_intent_envelope(mode="MOCK"),
        )


def test_route_execution_intent_rejects_unexpected_event_type() -> None:
    envelope = _intent_envelope(mode="MOCK")
    envelope["event_type"] = "agent.decision.action_proposed"
    with pytest.raises(ModeRoutingError):
        route_execution_intent(envelope)
