from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

import pytest

from services.agent_orchestrator.memory_layer import DecisionMemoryRecord
from services.agent_orchestrator.replay_service import (
    AgentMessageRecord,
    AgentRunRecord,
    DecisionReplayNotFoundError,
    DecisionReplayService,
    DecisionTraceRecord,
)
from services.llm_gateway.persistence import LLMCallRecord


class _FlakyOrderTraceStore:
    def __init__(
        self,
        *,
        decision_trace: DecisionTraceRecord | None,
        agent_runs: Sequence[AgentRunRecord],
        agent_messages: dict[str, Sequence[AgentMessageRecord]],
        llm_calls: Sequence[LLMCallRecord],
    ) -> None:
        self.decision_trace = decision_trace
        self.agent_runs = list(agent_runs)
        self.agent_messages = {key: list(value) for key, value in agent_messages.items()}
        self.llm_calls = list(llm_calls)
        self.reads = 0

    async def read_decision_trace(self, *, decision_id: str) -> DecisionTraceRecord | None:
        _ = decision_id
        return self.decision_trace

    async def list_agent_runs(self, *, decision_id: str) -> Sequence[AgentRunRecord]:
        _ = decision_id
        self.reads += 1
        runs = list(self.agent_runs)
        if self.reads % 2 == 0:
            runs.reverse()
        return runs

    async def list_agent_messages(self, *, agent_run_id: str) -> Sequence[AgentMessageRecord]:
        messages = list(self.agent_messages.get(agent_run_id, []))
        if self.reads % 2 == 0:
            messages.reverse()
        return messages

    async def list_llm_calls(self, *, decision_id: str) -> Sequence[LLMCallRecord]:
        _ = decision_id
        calls = list(self.llm_calls)
        if self.reads % 2 == 0:
            calls.reverse()
        return calls


class _FakeLongTermStore:
    def __init__(self, record: DecisionMemoryRecord | None) -> None:
        self.record = record

    async def read_decision_summary(self, *, decision_id: str) -> DecisionMemoryRecord | None:
        if self.record is None:
            return None
        if self.record.decision_id != decision_id:
            return None
        return self.record

    async def persist_decision_summary(self, record: DecisionMemoryRecord) -> None:
        self.record = record


def _decision_trace() -> DecisionTraceRecord:
    return DecisionTraceRecord(
        decision_id="b8eaf26d-c57f-45d2-af94-9b6f6ed5fbd5",
        trace_id="98f8e2f9-30e5-4e6c-acb0-d266fd7d62ab",
        strategy_id="9f0afec9-460c-45be-9b08-1c39f5f15384",
        mode="MOCK",
        status="RISK_APPROVED",
        started_at="2026-02-14T14:58:00Z",
        completed_at="2026-02-14T14:58:02Z",
    )


def _agent_runs() -> tuple[AgentRunRecord, ...]:
    return (
        AgentRunRecord(
            agent_run_id="run-risk",
            decision_id=_decision_trace().decision_id,
            agent_name="risk",
            input_ref="mem:decision:MOCK:strategy:decision:plan",
            output_ref="mem:decision:MOCK:strategy:decision:risk",
            latency_ms=11.3,
            status="SUCCEEDED",
            started_at="2026-02-14T14:58:01Z",
            completed_at="2026-02-14T14:58:01.2Z",
        ),
        AgentRunRecord(
            agent_run_id="run-planner",
            decision_id=_decision_trace().decision_id,
            agent_name="planner",
            input_ref="mem:decision:MOCK:strategy:decision:context",
            output_ref="mem:decision:MOCK:strategy:decision:plan",
            latency_ms=7.1,
            status="SUCCEEDED",
            started_at="2026-02-14T14:58:00.4Z",
            completed_at="2026-02-14T14:58:00.6Z",
        ),
    )


def _messages() -> dict[str, tuple[AgentMessageRecord, ...]]:
    return {
        "run-planner": (
            AgentMessageRecord(
                message_id="m2",
                agent_run_id="run-planner",
                role="assistant",
                payload_json={"action": "BUY"},
                created_at="2026-02-14T14:58:00.56Z",
            ),
            AgentMessageRecord(
                message_id="m1",
                agent_run_id="run-planner",
                role="system",
                payload_json={"instruction": "plan"},
                created_at="2026-02-14T14:58:00.45Z",
            ),
        ),
        "run-risk": (
            AgentMessageRecord(
                message_id="m3",
                agent_run_id="run-risk",
                role="assistant",
                payload_json={"approved": True},
                created_at="2026-02-14T14:58:01.1Z",
            ),
        ),
    }


def _llm_calls() -> tuple[LLMCallRecord, ...]:
    return (
        LLMCallRecord(
            llm_call_id="call-2",
            trace_id=_decision_trace().trace_id,
            decision_id=_decision_trace().decision_id,
            strategy_id=_decision_trace().strategy_id,
            agent_name="risk",
            provider="primary",
            model="gpt-4o-mini",
            prompt_payload={"messages": [{"role": "system", "content": "risk"}]},
            response_payload={"status": "succeeded", "content": "ok"},
            prompt_tokens=30,
            completion_tokens=10,
            total_tokens=40,
            latency_ms=21.0,
            estimated_cost=0.0011,
            created_at="2026-02-14T14:58:01.0Z",
        ),
        LLMCallRecord(
            llm_call_id="call-1",
            trace_id=_decision_trace().trace_id,
            decision_id=_decision_trace().decision_id,
            strategy_id=_decision_trace().strategy_id,
            agent_name="planner",
            provider="primary",
            model="gpt-4o-mini",
            prompt_payload={"messages": [{"role": "system", "content": "plan"}]},
            response_payload={"status": "succeeded", "content": "buy"},
            prompt_tokens=28,
            completion_tokens=8,
            total_tokens=36,
            latency_ms=19.0,
            estimated_cost=0.0010,
            created_at="2026-02-14T14:58:00.5Z",
        ),
    )


def _memory_record() -> DecisionMemoryRecord:
    trace = _decision_trace()
    return DecisionMemoryRecord(
        trace_id=trace.trace_id,
        decision_id=trace.decision_id,
        strategy_id=trace.strategy_id,
        mode=trace.mode,
        status=trace.status,
        summary={
            "status": "RISK_APPROVED",
            "plan": {"action": "BUY", "target_quantity": 0.2},
            "risk": {"approved": True, "risk_score": 0.95},
        },
        lifecycle=(
            {"event_type": "agent.decision.received"},
            {"event_type": "agent.decision.intent_published"},
        ),
        persisted_at="2026-02-14T14:58:02Z",
    )


@pytest.mark.asyncio
async def test_replay_service_reconstructs_decision_graph_and_payloads() -> None:
    trace = _decision_trace()
    service = DecisionReplayService(
        trace_store=_FlakyOrderTraceStore(
            decision_trace=trace,
            agent_runs=_agent_runs(),
            agent_messages=_messages(),
            llm_calls=_llm_calls(),
        ),
        long_term_store=_FakeLongTermStore(_memory_record()),
    )

    replay = await service.replay_decision(decision_id=trace.decision_id)

    assert replay.decision_id == trace.decision_id
    assert replay.status == "RISK_APPROVED"
    assert replay.summary["plan"]["action"] == "BUY"
    assert replay.lifecycle[-1]["event_type"] == "agent.decision.intent_published"
    assert replay.agent_runs[0]["agent_name"] == "planner"
    assert replay.agent_runs[0]["messages"][0]["message_id"] == "m1"
    assert replay.llm_calls[0]["llm_call_id"] == "call-1"
    node_types = {node.node_type for node in replay.graph_nodes}
    assert {"decision_trace", "agent_run", "llm_call", "memory_summary"} <= node_types
    assert any(edge.relation == "has_run" for edge in replay.graph_edges)
    assert any(edge.relation == "has_llm_call" for edge in replay.graph_edges)
    assert replay.deterministic_digest


@pytest.mark.asyncio
async def test_replay_service_digest_is_deterministic_for_same_payload() -> None:
    trace = _decision_trace()
    store = _FlakyOrderTraceStore(
        decision_trace=trace,
        agent_runs=_agent_runs(),
        agent_messages=_messages(),
        llm_calls=_llm_calls(),
    )
    service = DecisionReplayService(
        trace_store=store,
        long_term_store=_FakeLongTermStore(_memory_record()),
    )

    first = await service.replay_decision(decision_id=trace.decision_id)
    second = await service.replay_decision(decision_id=trace.decision_id)

    assert first.deterministic_digest == second.deterministic_digest
    assert first.graph_edges == second.graph_edges


@pytest.mark.asyncio
async def test_replay_service_raises_when_trace_not_found() -> None:
    trace = _decision_trace()
    service = DecisionReplayService(
        trace_store=_FlakyOrderTraceStore(
            decision_trace=None,
            agent_runs=(),
            agent_messages={},
            llm_calls=(),
        ),
        long_term_store=_FakeLongTermStore(replace(_memory_record(), decision_id="another-id")),
    )

    with pytest.raises(DecisionReplayNotFoundError):
        await service.replay_decision(decision_id=trace.decision_id)
