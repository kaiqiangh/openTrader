from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class RiskControlEvent:
    event_type: str
    control: str
    status: str
    reason: str
    actor: str
    occurred_at: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RiskControlGate:
    allowed: bool
    blocked_by: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RiskControlState:
    kill_switch_enabled: bool
    circuit_breaker_open: bool
    consecutive_failures: int
    circuit_breaker_open_until: str | None


class RiskControlPlane:
    """Maintains kill-switch and circuit-breaker state for OMS dispatch controls."""

    def __init__(
        self,
        *,
        circuit_breaker_threshold: int = 3,
        circuit_breaker_cooldown_seconds: int = 60,
    ) -> None:
        if circuit_breaker_threshold <= 0:
            raise ValueError("circuit_breaker_threshold must be positive")
        if circuit_breaker_cooldown_seconds <= 0:
            raise ValueError("circuit_breaker_cooldown_seconds must be positive")

        self._threshold = int(circuit_breaker_threshold)
        self._cooldown_seconds = int(circuit_breaker_cooldown_seconds)
        self._kill_switch_enabled = False
        self._consecutive_failures = 0
        self._circuit_breaker_open_until: datetime | None = None
        self._events: list[RiskControlEvent] = []

    def enable_kill_switch(self, *, reason: str, actor: str, at: datetime | None = None) -> None:
        now = _to_utc(at)
        if self._kill_switch_enabled:
            return

        self._kill_switch_enabled = True
        self._emit(
            event_type="risk.kill_switch.enabled",
            control="kill_switch",
            status="ENABLED",
            reason=reason,
            actor=actor,
            occurred_at=now,
        )

    def disable_kill_switch(self, *, reason: str, actor: str, at: datetime | None = None) -> None:
        now = _to_utc(at)
        if not self._kill_switch_enabled:
            return

        self._kill_switch_enabled = False
        self._emit(
            event_type="risk.kill_switch.disabled",
            control="kill_switch",
            status="DISABLED",
            reason=reason,
            actor=actor,
            occurred_at=now,
        )

    def record_failure(self, *, reason: str, actor: str, at: datetime | None = None) -> None:
        now = _to_utc(at)
        self._consecutive_failures += 1
        self._emit(
            event_type="risk.circuit_breaker.failure_recorded",
            control="circuit_breaker",
            status="FAILURE_RECORDED",
            reason=reason,
            actor=actor,
            occurred_at=now,
            metadata={"consecutive_failures": self._consecutive_failures},
        )

        if self._consecutive_failures >= self._threshold:
            self.trip_circuit_breaker(reason=reason, actor=actor, at=now)

    def record_success(self) -> None:
        self._consecutive_failures = 0

    def trip_circuit_breaker(
        self,
        *,
        reason: str,
        actor: str,
        at: datetime | None = None,
        cooldown_seconds: int | None = None,
    ) -> None:
        now = _to_utc(at)
        cooldown = int(cooldown_seconds or self._cooldown_seconds)
        if cooldown <= 0:
            raise ValueError("cooldown_seconds must be positive")

        open_until = now + timedelta(seconds=cooldown)
        self._circuit_breaker_open_until = open_until
        self._emit(
            event_type="risk.circuit_breaker.tripped",
            control="circuit_breaker",
            status="OPEN",
            reason=reason,
            actor=actor,
            occurred_at=now,
            metadata={
                "consecutive_failures": self._consecutive_failures,
                "threshold": self._threshold,
                "open_until": _to_iso(open_until),
            },
        )

    def reset_circuit_breaker(self, *, reason: str, actor: str, at: datetime | None = None) -> None:
        now = _to_utc(at)
        if self._circuit_breaker_open_until is None and self._consecutive_failures == 0:
            return

        self._circuit_breaker_open_until = None
        self._consecutive_failures = 0
        self._emit(
            event_type="risk.circuit_breaker.reset",
            control="circuit_breaker",
            status="CLOSED",
            reason=reason,
            actor=actor,
            occurred_at=now,
        )

    def evaluate_order_allowed(self, *, now: datetime | None = None) -> RiskControlGate:
        reference_time = _to_utc(now)
        self._auto_reset_if_expired(now=reference_time)

        blocked: list[str] = []
        if self._kill_switch_enabled:
            blocked.append("kill_switch")
        if self._is_circuit_breaker_open(now=reference_time):
            blocked.append("circuit_breaker")

        return RiskControlGate(allowed=not blocked, blocked_by=tuple(blocked))

    def snapshot(self, *, now: datetime | None = None) -> RiskControlState:
        reference_time = _to_utc(now)
        self._auto_reset_if_expired(now=reference_time)
        open_until = (
            _to_iso(self._circuit_breaker_open_until)
            if self._circuit_breaker_open_until is not None
            else None
        )
        return RiskControlState(
            kill_switch_enabled=self._kill_switch_enabled,
            circuit_breaker_open=self._is_circuit_breaker_open(now=reference_time),
            consecutive_failures=self._consecutive_failures,
            circuit_breaker_open_until=open_until,
        )

    def drain_events(self) -> tuple[RiskControlEvent, ...]:
        drained = tuple(self._events)
        self._events.clear()
        return drained

    def _is_circuit_breaker_open(self, *, now: datetime) -> bool:
        if self._circuit_breaker_open_until is None:
            return False
        return now < self._circuit_breaker_open_until

    def _auto_reset_if_expired(self, *, now: datetime) -> None:
        if self._circuit_breaker_open_until is None:
            return

        if now < self._circuit_breaker_open_until:
            return

        self._circuit_breaker_open_until = None
        self._consecutive_failures = 0
        self._emit(
            event_type="risk.circuit_breaker.auto_reset",
            control="circuit_breaker",
            status="CLOSED",
            reason="cooldown elapsed",
            actor="system",
            occurred_at=now,
        )

    def _emit(
        self,
        *,
        event_type: str,
        control: str,
        status: str,
        reason: str,
        actor: str,
        occurred_at: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._events.append(
            RiskControlEvent(
                event_type=event_type,
                control=control,
                status=status,
                reason=reason,
                actor=actor,
                occurred_at=_to_iso(occurred_at),
                metadata=metadata or {},
            )
        )


def _to_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _to_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
