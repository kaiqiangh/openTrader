from __future__ import annotations

from services.agent_orchestrator.metrics_tracing import AgentRuntimeMetrics


def test_metrics_snapshot_exposes_stage_latency_failure_and_token_totals() -> None:
    metrics = AgentRuntimeMetrics()

    metrics.record_stage_success(
        trace_id="trace-1",
        decision_id="decision-1",
        mode="MOCK",
        stage="planner_agent",
        latency_ms=12.5,
    )
    metrics.record_stage_failure(
        trace_id="trace-1",
        decision_id="decision-1",
        mode="MOCK",
        stage="risk_agent",
        latency_ms=7.2,
        error_type="RuntimeError",
    )
    metrics.record_llm_call(
        trace_id="trace-1",
        decision_id="decision-1",
        strategy_id="strategy-1",
        agent_name="planner",
        provider="primary",
        model="gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=60,
        total_tokens=160,
        latency_ms=19.0,
        estimated_cost=0.002,
        status="succeeded",
    )

    snapshot = metrics.snapshot()

    planner_stage = snapshot["agent_stages"]["planner_agent"]
    assert planner_stage["runs_total"] == 1
    assert planner_stage["failures_total"] == 0
    assert planner_stage["avg_latency_ms"] == 12.5
    risk_stage = snapshot["agent_stages"]["risk_agent"]
    assert risk_stage["runs_total"] == 1
    assert risk_stage["failures_total"] == 1
    assert risk_stage["failure_rate"] == 1.0
    llm_totals = snapshot["llm_usage"]["totals"]
    assert llm_totals["calls_total"] == 1
    assert llm_totals["tokens_total"] == 160
    assert llm_totals["estimated_cost_total"] == 0.002
    spans = snapshot["recent_spans"]
    assert spans[0]["stage"] == "planner_agent"
    assert spans[1]["status"] == "failed"
