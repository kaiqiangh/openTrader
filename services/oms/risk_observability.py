from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final

from services.oms.risk_controls import RiskControlEvent
from services.oms.risk_policy import RiskPolicyDecision
from services.oms.risk_rules import ProposedOrder

_CRITICAL_BLOCKERS: Final[frozenset[str]] = frozenset({"kill_switch", "circuit_breaker"})
_WARNING_BLOCKERS: Final[frozenset[str]] = frozenset(
    {
        "position_limit",
        "symbol_notional_limit",
        "leverage_limit",
        "drawdown_limit",
        "daily_loss_limit",
    }
)


@dataclass(frozen=True, slots=True)
class RiskObservabilityEvent:
    event_type: str
    severity: str
    occurred_at: str
    trace_id: str | None
    decision_id: str | None
    strategy_id: str | None
    metadata: dict[str, Any]


class RiskObservabilityCollector:
    """Collects risk policy telemetry counters and structured events."""

    def __init__(self) -> None:
        self._totals: dict[str, int] = {
            "evaluations_total": 0,
            "allowed_total": 0,
            "denied_total": 0,
            "control_events_total": 0,
        }
        self._blocked_by: dict[str, int] = {}
        self._control_events: dict[str, int] = {}
        self._events: list[RiskObservabilityEvent] = []

    def record_policy_decision(
        self,
        *,
        trace_id: str | None,
        decision_id: str | None,
        strategy_id: str | None,
        order: ProposedOrder,
        decision: RiskPolicyDecision,
    ) -> None:
        self._totals["evaluations_total"] += 1
        if decision.allowed:
            self._totals["allowed_total"] += 1
        else:
            self._totals["denied_total"] += 1
            for reason in decision.blocked_by:
                self._blocked_by[reason] = self._blocked_by.get(reason, 0) + 1

        event_type = "risk.policy.allowed" if decision.allowed else "risk.policy.denied"
        event = RiskObservabilityEvent(
            event_type=event_type,
            severity=_policy_severity(decision.blocked_by),
            occurred_at=_utc_now_iso(),
            trace_id=trace_id,
            decision_id=decision_id,
            strategy_id=strategy_id,
            metadata={
                "mode": order.mode,
                "symbol": order.symbol,
                "side": order.side,
                "quantity": order.quantity,
                "price": order.price,
                "blocked_by": list(decision.blocked_by),
                "projected_position_qty": decision.core.projected_position_qty,
                "projected_symbol_notional_usd": decision.core.projected_symbol_notional_usd,
                "projected_leverage": decision.core.projected_leverage,
                "drawdown_pct": decision.guards.drawdown_pct,
                "daily_loss_usd": decision.guards.daily_loss_usd,
            },
        )
        self._events.append(event)

    def record_control_events(self, *, events: tuple[RiskControlEvent, ...]) -> None:
        if not events:
            return

        for event in events:
            self._totals["control_events_total"] += 1
            self._control_events[event.event_type] = self._control_events.get(event.event_type, 0) + 1

            self._events.append(
                RiskObservabilityEvent(
                    event_type=f"risk.control.{event.event_type}",
                    severity=_control_severity(event.event_type),
                    occurred_at=event.occurred_at,
                    trace_id=None,
                    decision_id=None,
                    strategy_id=None,
                    metadata={
                        "control": event.control,
                        "status": event.status,
                        "reason": event.reason,
                        "actor": event.actor,
                        "metadata": dict(event.metadata),
                    },
                )
            )

    def snapshot(self) -> dict[str, Any]:
        return {
            "totals": dict(self._totals),
            "blocked_by": dict(sorted(self._blocked_by.items())),
            "control_events": dict(sorted(self._control_events.items())),
            "recent_events": [
                {
                    "event_type": event.event_type,
                    "severity": event.severity,
                    "occurred_at": event.occurred_at,
                    "trace_id": event.trace_id,
                    "decision_id": event.decision_id,
                    "strategy_id": event.strategy_id,
                    "metadata": dict(event.metadata),
                }
                for event in self._events[-100:]
            ],
        }

    def drain_events(self) -> tuple[RiskObservabilityEvent, ...]:
        drained = tuple(self._events)
        self._events.clear()
        return drained


def _policy_severity(blocked_by: tuple[str, ...]) -> str:
    if not blocked_by:
        return "INFO"

    blocked = set(blocked_by)
    if blocked & _CRITICAL_BLOCKERS:
        return "CRITICAL"
    if blocked & _WARNING_BLOCKERS:
        return "WARNING"
    return "WARNING"


def _control_severity(event_type: str) -> str:
    if event_type in {"risk.kill_switch.enabled", "risk.circuit_breaker.tripped"}:
        return "CRITICAL"
    if event_type in {"risk.circuit_breaker.failure_recorded"}:
        return "WARNING"
    return "INFO"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
