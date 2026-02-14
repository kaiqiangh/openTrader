from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class ExecutionTraceSpan:
    trace_id: str
    decision_id: str
    mode: str
    stage: str
    status: str
    latency_ms: float
    error_type: str | None
    started_at: str
    completed_at: str


class SimulationExecutionMetrics:
    """In-memory metrics collector for simulation execution worker stages."""

    def __init__(self) -> None:
        self._runs_total = 0
        self._success_total = 0
        self._failure_total = 0
        self._events_published_total = 0
        self._latencies_ms: list[float] = []
        self._spans: list[ExecutionTraceSpan] = []

    def record_success(
        self,
        *,
        trace_id: str,
        decision_id: str,
        mode: str,
        stage: str,
        latency_ms: float,
        events_published: int,
        started_at: str,
        completed_at: str,
    ) -> None:
        self._runs_total += 1
        self._success_total += 1
        self._events_published_total += max(0, int(events_published))
        self._latencies_ms.append(float(latency_ms))
        self._spans.append(
            ExecutionTraceSpan(
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                stage=stage,
                status="succeeded",
                latency_ms=float(latency_ms),
                error_type=None,
                started_at=started_at,
                completed_at=completed_at,
            )
        )

    def record_failure(
        self,
        *,
        trace_id: str,
        decision_id: str,
        mode: str,
        stage: str,
        latency_ms: float,
        error_type: str,
        started_at: str,
        completed_at: str,
    ) -> None:
        self._runs_total += 1
        self._failure_total += 1
        self._latencies_ms.append(float(latency_ms))
        self._spans.append(
            ExecutionTraceSpan(
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                stage=stage,
                status="failed",
                latency_ms=float(latency_ms),
                error_type=error_type,
                started_at=started_at,
                completed_at=completed_at,
            )
        )

    def snapshot(self) -> dict[str, Any]:
        avg_latency = (sum(self._latencies_ms) / len(self._latencies_ms)) if self._latencies_ms else None
        max_latency = max(self._latencies_ms) if self._latencies_ms else None
        failure_rate = (self._failure_total / self._runs_total) if self._runs_total else 0.0
        return {
            "totals": {
                "runs_total": self._runs_total,
                "success_total": self._success_total,
                "failure_total": self._failure_total,
                "failure_rate": failure_rate,
                "events_published_total": self._events_published_total,
            },
            "latency_ms": {
                "avg": avg_latency,
                "max": max_latency,
            },
            "recent_spans": [asdict(span) for span in self._spans[-100:]],
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
