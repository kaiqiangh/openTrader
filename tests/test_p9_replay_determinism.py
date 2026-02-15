from __future__ import annotations

import pytest

from services.agent_orchestrator.memory_layer import DecisionMemoryRecord
from services.agent_orchestrator.replay_service import AgentMessageRecord, AgentRunRecord, DecisionTraceRecord
from services.api.state import build_default_state
from services.llm_gateway.persistence import LLMCallRecord


def _seed_replay_records() -> tuple[
    DecisionTraceRecord,
    tuple[AgentRunRecord, ...],
    dict[str, tuple[AgentMessageRecord, ...]],
    tuple[LLMCallRecord, ...],
    DecisionMemoryRecord,
]:
    trace = DecisionTraceRecord(
        decision_id="6e7dc95f-9220-4fef-a795-4470eec8482e",
        trace_id="a43c8fef-b320-40cc-8f6c-7d048f2df7dc",
        strategy_id="btc-momentum",
        mode="MOCK",
        status="RISK_APPROVED",
        started_at="2026-02-15T01:00:00Z",
        completed_at="2026-02-15T01:00:03Z",
    )
    runs = (
        AgentRunRecord(
            agent_run_id="run-risk",
            decision_id=trace.decision_id,
            agent_name="risk",
            input_ref="mem:risk:in",
            output_ref="mem:risk:out",
            latency_ms=11.2,
            status="SUCCEEDED",
            started_at="2026-02-15T01:00:02Z",
            completed_at="2026-02-15T01:00:02.4Z",
        ),
        AgentRunRecord(
            agent_run_id="run-planner",
            decision_id=trace.decision_id,
            agent_name="planner",
            input_ref="mem:plan:in",
            output_ref="mem:plan:out",
            latency_ms=9.4,
            status="SUCCEEDED",
            started_at="2026-02-15T01:00:01Z",
            completed_at="2026-02-15T01:00:01.3Z",
        ),
    )
    messages = {
        "run-planner": (
            AgentMessageRecord(
                message_id="planner-2",
                agent_run_id="run-planner",
                role="assistant",
                payload_json={"action": "BUY", "confidence": 0.78},
                created_at="2026-02-15T01:00:01.25Z",
            ),
            AgentMessageRecord(
                message_id="planner-1",
                agent_run_id="run-planner",
                role="system",
                payload_json={"instruction": "build plan"},
                created_at="2026-02-15T01:00:01.05Z",
            ),
        ),
        "run-risk": (
            AgentMessageRecord(
                message_id="risk-1",
                agent_run_id="run-risk",
                role="assistant",
                payload_json={"approved": True, "risk_score": 0.92},
                created_at="2026-02-15T01:00:02.2Z",
            ),
        ),
    }
    llm_calls = (
        LLMCallRecord(
            llm_call_id="llm-risk",
            trace_id=trace.trace_id,
            decision_id=trace.decision_id,
            strategy_id=trace.strategy_id,
            agent_name="risk",
            provider="primary",
            model="gpt-4o-mini",
            prompt_payload={"messages": [{"role": "system", "content": "risk"}]},
            response_payload={"status": "succeeded", "content": "approved"},
            prompt_tokens=22,
            completion_tokens=7,
            total_tokens=29,
            latency_ms=20.1,
            estimated_cost=0.0009,
            created_at="2026-02-15T01:00:02.1Z",
        ),
        LLMCallRecord(
            llm_call_id="llm-planner",
            trace_id=trace.trace_id,
            decision_id=trace.decision_id,
            strategy_id=trace.strategy_id,
            agent_name="planner",
            provider="primary",
            model="gpt-4o-mini",
            prompt_payload={"messages": [{"role": "system", "content": "plan"}]},
            response_payload={"status": "succeeded", "content": "buy"},
            prompt_tokens=19,
            completion_tokens=6,
            total_tokens=25,
            latency_ms=17.3,
            estimated_cost=0.0008,
            created_at="2026-02-15T01:00:01.1Z",
        ),
    )
    memory = DecisionMemoryRecord(
        trace_id=trace.trace_id,
        decision_id=trace.decision_id,
        strategy_id=trace.strategy_id,
        mode=trace.mode,
        status=trace.status,
        summary={
            "status": "RISK_APPROVED",
            "plan": {"action": "BUY", "target_quantity": 0.15},
            "risk": {"approved": True, "risk_score": 0.92},
        },
        lifecycle=(
            {"event_type": "agent.decision.received"},
            {"event_type": "agent.decision.context_enriched"},
            {"event_type": "agent.decision.planned"},
            {"event_type": "agent.decision.risk_approved"},
            {"event_type": "agent.decision.action_proposed"},
            {"event_type": "agent.decision.guardrail_passed"},
            {"event_type": "agent.decision.intent_published"},
        ),
        persisted_at="2026-02-15T01:00:03.1Z",
    )
    return trace, runs, messages, llm_calls, memory


@pytest.mark.asyncio
async def test_p9_replay_determinism_reproduces_stored_decision_chain() -> None:
    trace, runs, messages, llm_calls, memory = _seed_replay_records()
    state = build_default_state(default_mode="MOCK")
    state.replay_traces[trace.decision_id] = trace
    state.replay_agent_runs[trace.decision_id] = list(runs)
    state.replay_agent_messages = {run_id: list(items) for run_id, items in messages.items()}
    state.replay_llm_calls[trace.decision_id] = list(llm_calls)
    state.replay_summaries[trace.decision_id] = memory

    first = await state.replay_decision(decision_id=trace.decision_id)
    second = await state.replay_decision(decision_id=trace.decision_id)

    assert first.deterministic_digest == second.deterministic_digest
    assert [item["event_type"] for item in first.lifecycle] == [
        "agent.decision.received",
        "agent.decision.context_enriched",
        "agent.decision.planned",
        "agent.decision.risk_approved",
        "agent.decision.action_proposed",
        "agent.decision.guardrail_passed",
        "agent.decision.intent_published",
    ]
    assert [item["agent_name"] for item in first.agent_runs] == ["planner", "risk"]
    assert [item["messages"][0]["message_id"] for item in first.agent_runs] == ["planner-1", "risk-1"]
    assert [item["llm_call_id"] for item in first.llm_calls] == ["llm-planner", "llm-risk"]
    assert any(edge.relation == "has_summary" for edge in first.graph_edges)


@pytest.mark.asyncio
async def test_p9_replay_request_record_uses_same_deterministic_digest() -> None:
    trace, runs, messages, llm_calls, memory = _seed_replay_records()
    state = build_default_state(default_mode="MOCK")
    state.replay_traces[trace.decision_id] = trace
    state.replay_agent_runs[trace.decision_id] = list(runs)
    state.replay_agent_messages = {run_id: list(items) for run_id, items in messages.items()}
    state.replay_llm_calls[trace.decision_id] = list(llm_calls)
    state.replay_summaries[trace.decision_id] = memory

    direct = await state.replay_decision(decision_id=trace.decision_id)
    request_record = await state.submit_replay_request(
        decision_id=trace.decision_id,
        requested_by="qa-user",
    )

    assert request_record.status == "COMPLETED"
    assert request_record.result.decision_id == trace.decision_id
    assert request_record.result.deterministic_digest == direct.deterministic_digest
