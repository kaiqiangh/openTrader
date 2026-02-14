from __future__ import annotations

from datetime import datetime, timezone

from services.oms.risk_controls import RiskControlPlane


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def test_kill_switch_blocks_orders_and_emits_events() -> None:
    controls = RiskControlPlane(circuit_breaker_threshold=3, circuit_breaker_cooldown_seconds=60)

    controls.enable_kill_switch(reason="operator request", actor="ops", at=_ts("2026-02-14T16:30:00Z"))
    allowed = controls.evaluate_order_allowed(now=_ts("2026-02-14T16:30:05Z"))

    assert allowed.allowed is False
    assert "kill_switch" in allowed.blocked_by

    events = controls.drain_events()
    assert [event.event_type for event in events] == ["risk.kill_switch.enabled"]


def test_circuit_breaker_trips_after_threshold_failures_and_resets() -> None:
    controls = RiskControlPlane(circuit_breaker_threshold=2, circuit_breaker_cooldown_seconds=30)

    controls.record_failure(reason="exchange disconnect", actor="runner", at=_ts("2026-02-14T16:31:00Z"))
    first_check = controls.evaluate_order_allowed(now=_ts("2026-02-14T16:31:01Z"))
    assert first_check.allowed is True

    controls.record_failure(reason="exchange disconnect", actor="runner", at=_ts("2026-02-14T16:31:05Z"))
    second_check = controls.evaluate_order_allowed(now=_ts("2026-02-14T16:31:06Z"))
    assert second_check.allowed is False
    assert "circuit_breaker" in second_check.blocked_by

    controls.reset_circuit_breaker(reason="operator reset", actor="ops", at=_ts("2026-02-14T16:31:10Z"))
    final_check = controls.evaluate_order_allowed(now=_ts("2026-02-14T16:31:11Z"))
    assert final_check.allowed is True


def test_circuit_breaker_auto_closes_after_cooldown() -> None:
    controls = RiskControlPlane(circuit_breaker_threshold=1, circuit_breaker_cooldown_seconds=10)

    controls.record_failure(reason="risk breach", actor="risk", at=_ts("2026-02-14T16:32:00Z"))
    blocked_now = controls.evaluate_order_allowed(now=_ts("2026-02-14T16:32:05Z"))
    assert blocked_now.allowed is False

    unblocked_after_cooldown = controls.evaluate_order_allowed(now=_ts("2026-02-14T16:32:11Z"))
    assert unblocked_after_cooldown.allowed is True
