from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from services.notification_service.models import DeliveryResult, NotificationEvent


@dataclass(frozen=True, slots=True)
class NotificationTraceSpan:
    notification_event_id: str
    trace_id: str
    decision_id: str
    stage: str
    status: str
    latency_ms: float
    gateway: str | None
    attempt: int | None
    started_at: str
    completed_at: str


@dataclass(frozen=True, slots=True)
class NotificationDeliveryLog:
    notification_event_id: str
    trace_id: str
    decision_id: str
    event_type: str
    severity: str
    gateway: str
    delivery_status: str
    attempt: int
    detail: str | None
    logged_at: str


class NotificationObservabilityCollector:
    """In-memory notification telemetry collector for metrics/logs/traces."""

    def __init__(self, *, max_records: int = 200) -> None:
        if max_records <= 0:
            raise ValueError("max_records must be positive")
        self._max_records = int(max_records)
        self._totals: dict[str, int] = {
            "received_total": 0,
            "filtered_total": 0,
            "dispatched_total": 0,
            "delivered_total": 0,
            "failed_total": 0,
            "retryable_total": 0,
            "dlq_total": 0,
        }
        self._suppression: dict[str, int] = {"dedupe": 0, "rate_limit": 0}
        self._gateway_status: dict[str, int] = {}
        self._retry_attempt_histogram: dict[str, int] = {}
        self._recent_logs: list[NotificationDeliveryLog] = []
        self._recent_spans: list[NotificationTraceSpan] = []

    def record_event_received(self) -> None:
        self._totals["received_total"] += 1

    def record_policy_result(
        self,
        *,
        event: NotificationEvent,
        messages_count: int,
        suppression_delta: Mapping[str, int],
        latency_ms: float,
        started_at: str,
        completed_at: str,
    ) -> None:
        filtered = sum(max(0, int(value)) for value in suppression_delta.values())
        self._totals["filtered_total"] += filtered
        for key in ("dedupe", "rate_limit"):
            self._suppression[key] += max(0, int(suppression_delta.get(key, 0)))

        status = "filtered" if messages_count == 0 else "routed"
        self._append_span(
            NotificationTraceSpan(
                notification_event_id=event.notification_event_id,
                trace_id=event.trace_id,
                decision_id=event.decision_id,
                stage="policy_router",
                status=status,
                latency_ms=float(latency_ms),
                gateway=None,
                attempt=None,
                started_at=started_at,
                completed_at=completed_at,
            )
        )

    def record_dispatch_result(
        self,
        *,
        event: NotificationEvent,
        results: tuple[DeliveryResult, ...],
        dlq_delta: int,
        latency_ms: float,
        started_at: str,
        completed_at: str,
    ) -> None:
        self._totals["dispatched_total"] += len(results)
        self._totals["dlq_total"] += max(0, int(dlq_delta))

        for result in results:
            status = result.status.strip().upper()
            if status == "DELIVERED":
                self._totals["delivered_total"] += 1
            elif status in {"RETRYABLE", "RETRYABLE_ERROR", "FAILED_RETRYABLE"}:
                self._totals["retryable_total"] += 1
            else:
                self._totals["failed_total"] += 1

            gateway_status_key = f"{result.gateway}:{status}"
            self._gateway_status[gateway_status_key] = (
                self._gateway_status.get(gateway_status_key, 0) + 1
            )

            attempt_bucket = str(max(1, int(result.attempt)))
            self._retry_attempt_histogram[attempt_bucket] = (
                self._retry_attempt_histogram.get(attempt_bucket, 0) + 1
            )
            if result.attempt > 1:
                self._totals["retryable_total"] += result.attempt - 1

            self._append_log(
                NotificationDeliveryLog(
                    notification_event_id=event.notification_event_id,
                    trace_id=event.trace_id,
                    decision_id=event.decision_id,
                    event_type=event.event_type,
                    severity=event.severity.value,
                    gateway=result.gateway,
                    delivery_status=status,
                    attempt=int(result.attempt),
                    detail=result.detail,
                    logged_at=completed_at,
                )
            )

        dispatch_status = "succeeded"
        if any(result.status.strip().upper() != "DELIVERED" for result in results):
            dispatch_status = (
                "partial_failure"
                if any(result.status.strip().upper() == "DELIVERED" for result in results)
                else "failed"
            )

        self._append_span(
            NotificationTraceSpan(
                notification_event_id=event.notification_event_id,
                trace_id=event.trace_id,
                decision_id=event.decision_id,
                stage="gateway_dispatch",
                status=dispatch_status,
                latency_ms=float(latency_ms),
                gateway=None,
                attempt=None,
                started_at=started_at,
                completed_at=completed_at,
            )
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "totals": dict(self._totals),
            "suppression": dict(self._suppression),
            "gateway_status": dict(sorted(self._gateway_status.items())),
            "retry_attempt_histogram": dict(sorted(self._retry_attempt_histogram.items())),
            "recent_logs": [asdict(item) for item in self._recent_logs[-self._max_records :]],
            "recent_spans": [asdict(item) for item in self._recent_spans[-self._max_records :]],
            "generated_at": _utc_now_iso(),
        }

    def _append_log(self, log: NotificationDeliveryLog) -> None:
        self._recent_logs.append(log)
        if len(self._recent_logs) > self._max_records:
            del self._recent_logs[: len(self._recent_logs) - self._max_records]

    def _append_span(self, span: NotificationTraceSpan) -> None:
        self._recent_spans.append(span)
        if len(self._recent_spans) > self._max_records:
            del self._recent_spans[: len(self._recent_spans) - self._max_records]


def utc_now_iso() -> str:
    return _utc_now_iso()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
