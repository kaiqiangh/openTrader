from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class TraceSpan:
    trace_id: str
    decision_id: str
    mode: str
    stage: str
    status: str
    latency_ms: float
    error_type: str | None
    started_at: str
    completed_at: str


class AgentRuntimeMetrics:
    def __init__(self) -> None:
        self._stage_runs: dict[str, int] = {}
        self._stage_failures: dict[str, int] = {}
        self._stage_latency_ms: dict[str, list[float]] = {}
        self._llm_totals: dict[str, float] = {
            "calls_total": 0.0,
            "failed_calls_total": 0.0,
            "prompt_tokens_total": 0.0,
            "completion_tokens_total": 0.0,
            "tokens_total": 0.0,
            "estimated_cost_total": 0.0,
        }
        self._llm_by_scope: dict[str, dict[str, float]] = {}
        self._spans: list[TraceSpan] = []

    def record_stage_success(
        self,
        *,
        trace_id: str,
        decision_id: str,
        mode: str,
        stage: str,
        latency_ms: float,
    ) -> None:
        self._stage_runs[stage] = self._stage_runs.get(stage, 0) + 1
        self._stage_latency_ms.setdefault(stage, []).append(float(latency_ms))
        self._spans.append(
            TraceSpan(
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                stage=stage,
                status="succeeded",
                latency_ms=float(latency_ms),
                error_type=None,
                started_at=_utc_now_iso(),
                completed_at=_utc_now_iso(),
            )
        )

    def record_stage_failure(
        self,
        *,
        trace_id: str,
        decision_id: str,
        mode: str,
        stage: str,
        latency_ms: float,
        error_type: str,
    ) -> None:
        self._stage_runs[stage] = self._stage_runs.get(stage, 0) + 1
        self._stage_failures[stage] = self._stage_failures.get(stage, 0) + 1
        self._stage_latency_ms.setdefault(stage, []).append(float(latency_ms))
        self._spans.append(
            TraceSpan(
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                stage=stage,
                status="failed",
                latency_ms=float(latency_ms),
                error_type=error_type,
                started_at=_utc_now_iso(),
                completed_at=_utc_now_iso(),
            )
        )

    def record_llm_call(
        self,
        *,
        trace_id: str,
        decision_id: str,
        strategy_id: str,
        agent_name: str,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        latency_ms: float,
        estimated_cost: float,
        status: str,
    ) -> None:
        _ = trace_id, decision_id, provider, model, latency_ms
        self._llm_totals["calls_total"] += 1
        self._llm_totals["prompt_tokens_total"] += int(prompt_tokens)
        self._llm_totals["completion_tokens_total"] += int(completion_tokens)
        self._llm_totals["tokens_total"] += int(total_tokens)
        self._llm_totals["estimated_cost_total"] += float(estimated_cost)
        if status != "succeeded":
            self._llm_totals["failed_calls_total"] += 1

        scope = f"{strategy_id}:{agent_name}"
        scoped = self._llm_by_scope.setdefault(
            scope,
            {
                "calls_total": 0.0,
                "failed_calls_total": 0.0,
                "prompt_tokens_total": 0.0,
                "completion_tokens_total": 0.0,
                "tokens_total": 0.0,
                "estimated_cost_total": 0.0,
            },
        )
        scoped["calls_total"] += 1
        scoped["prompt_tokens_total"] += int(prompt_tokens)
        scoped["completion_tokens_total"] += int(completion_tokens)
        scoped["tokens_total"] += int(total_tokens)
        scoped["estimated_cost_total"] += float(estimated_cost)
        if status != "succeeded":
            scoped["failed_calls_total"] += 1

    def snapshot(self) -> dict[str, Any]:
        agent_stages: dict[str, Any] = {}
        stage_names = set(self._stage_runs) | set(self._stage_failures) | set(self._stage_latency_ms)
        for stage in sorted(stage_names):
            runs = self._stage_runs.get(stage, 0)
            failures = self._stage_failures.get(stage, 0)
            latencies = self._stage_latency_ms.get(stage, [])
            avg_latency = (sum(latencies) / len(latencies)) if latencies else None
            max_latency = max(latencies) if latencies else None
            failure_rate = (failures / runs) if runs else 0.0
            agent_stages[stage] = {
                "runs_total": runs,
                "failures_total": failures,
                "failure_rate": failure_rate,
                "avg_latency_ms": avg_latency,
                "max_latency_ms": max_latency,
            }

        return {
            "agent_stages": agent_stages,
            "llm_usage": {
                "totals": _coerce_metric_types(self._llm_totals),
                "by_scope": {
                    scope: _coerce_metric_types(values) for scope, values in sorted(self._llm_by_scope.items())
                },
            },
            "recent_spans": [asdict(span) for span in self._spans[-100:]],
        }


def _coerce_metric_types(values: Mapping[str, float]) -> dict[str, int | float]:
    result: dict[str, int | float] = {}
    for key, value in values.items():
        if key.endswith("_total") and key != "estimated_cost_total":
            result[key] = int(value)
        else:
            result[key] = float(value)
    return result


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
