from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NotificationSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


_SEVERITY_RANK = {
    NotificationSeverity.INFO: 1,
    NotificationSeverity.WARNING: 2,
    NotificationSeverity.CRITICAL: 3,
}


def severity_rank(severity: NotificationSeverity) -> int:
    return _SEVERITY_RANK[severity]


@dataclass(frozen=True, slots=True)
class NotificationEvent:
    notification_event_id: str
    trace_id: str
    decision_id: str
    mode: str
    event_type: str
    severity: NotificationSeverity
    idempotency_key: str
    emitted_at: str
    service: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class NotificationPreference:
    user_id: str
    min_severity: NotificationSeverity = NotificationSeverity.INFO
    gateways: tuple[str, ...] = ("telegram",)
    strategy_ids: tuple[str, ...] = ()
    event_types: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NotificationMessage:
    message_id: str
    user_id: str
    gateway: str
    severity: NotificationSeverity
    title: str
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    message_id: str
    gateway: str
    status: str
    attempt: int
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class NotificationProcessingResult:
    event: NotificationEvent
    messages: tuple[NotificationMessage, ...]
    results: tuple[DeliveryResult, ...]
