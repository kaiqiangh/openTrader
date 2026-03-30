from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Final

from services.notification_service.models import (
    NotificationEvent,
    NotificationMessage,
    NotificationPreference,
    NotificationSeverity,
    severity_rank,
)

_MINUTE_SECONDS: Final[float] = 60.0


@dataclass(slots=True)
class NotificationPolicyRouter:
    preferences: tuple[NotificationPreference, ...] = ()
    dedupe_window_seconds: float = 120.0
    rate_limit_per_minute: int = 30
    _dedupe_seen_at: dict[tuple[str, str, str], float] = field(default_factory=dict, init=False)
    _rate_events: dict[tuple[str, str], list[float]] = field(default_factory=dict, init=False)
    _suppressed_counts: dict[str, int] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.dedupe_window_seconds <= 0:
            raise ValueError("dedupe_window_seconds must be positive")
        if self.rate_limit_per_minute <= 0:
            raise ValueError("rate_limit_per_minute must be positive")

        self._dedupe_seen_at.clear()
        self._rate_events.clear()
        self._suppressed_counts = {"dedupe": 0, "rate_limit": 0}

    def route(
        self, *, event: NotificationEvent, now_seconds: float
    ) -> tuple[NotificationMessage, ...]:
        active_prefs = self.preferences or (
            NotificationPreference(user_id="ops-default", min_severity=NotificationSeverity.INFO),
        )

        messages: list[NotificationMessage] = []
        for pref in active_prefs:
            if not _matches_preference(pref=pref, event=event):
                continue

            for gateway in pref.gateways:
                dedupe_key = (pref.user_id, gateway, event.idempotency_key)
                previous = self._dedupe_seen_at.get(dedupe_key)
                if previous is not None and (now_seconds - previous) < self.dedupe_window_seconds:
                    self._suppressed_counts["dedupe"] += 1
                    continue

                if not self._consume_rate_budget(
                    user_id=pref.user_id, gateway=gateway, now_seconds=now_seconds
                ):
                    self._suppressed_counts["rate_limit"] += 1
                    continue

                self._dedupe_seen_at[dedupe_key] = now_seconds
                messages.append(
                    NotificationMessage(
                        message_id=_message_id(
                            user_id=pref.user_id,
                            gateway=gateway,
                            event_id=event.notification_event_id,
                        ),
                        user_id=pref.user_id,
                        gateway=gateway,
                        severity=event.severity,
                        title=f"[{event.severity.value}] {event.event_type}",
                        body=_render_body(event=event),
                        metadata={
                            "trace_id": event.trace_id,
                            "decision_id": event.decision_id,
                            "event_type": event.event_type,
                            "service": event.service,
                            "mode": event.mode,
                        },
                    )
                )

        return tuple(messages)

    def suppression_counts(self) -> dict[str, int]:
        return dict(self._suppressed_counts)

    def _consume_rate_budget(self, *, user_id: str, gateway: str, now_seconds: float) -> bool:
        key = (user_id, gateway)
        entries = self._rate_events.setdefault(key, [])
        cutoff = now_seconds - _MINUTE_SECONDS
        entries[:] = [timestamp for timestamp in entries if timestamp >= cutoff]
        if len(entries) >= self.rate_limit_per_minute:
            return False
        entries.append(now_seconds)
        return True


def _matches_preference(*, pref: NotificationPreference, event: NotificationEvent) -> bool:
    if severity_rank(event.severity) < severity_rank(pref.min_severity):
        return False

    if pref.event_types and event.event_type not in pref.event_types:
        return False

    if pref.strategy_ids:
        strategy_id = str(event.payload.get("strategy_id", ""))
        if strategy_id not in pref.strategy_ids:
            return False

    return True


def _message_id(*, user_id: str, gateway: str, event_id: str) -> str:
    digest = sha256(f"{user_id}|{gateway}|{event_id}".encode("utf-8")).hexdigest()[:16]
    return f"msg-{digest}"


def _render_body(*, event: NotificationEvent) -> str:
    strategy = str(event.payload.get("strategy_id", "n/a"))
    symbol = str(event.payload.get("symbol", "n/a"))
    reason = str(event.payload.get("reason", ""))
    suffix = f" reason={reason}" if reason else ""
    return (
        f"event={event.event_type} severity={event.severity.value} strategy={strategy} "
        f"symbol={symbol} mode={event.mode}{suffix}"
    )
