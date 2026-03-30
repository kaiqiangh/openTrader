from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Protocol, Sequence

from services.agent_orchestrator.memory_layer import LongTermMemoryStore
from services.llm_gateway.persistence import LLMCallRecord


@dataclass(frozen=True, slots=True)
class DecisionTraceRecord:
    decision_id: str
    trace_id: str
    strategy_id: str
    mode: str
    status: str
    started_at: str
    completed_at: str | None


@dataclass(frozen=True, slots=True)
class AgentRunRecord:
    agent_run_id: str
    decision_id: str
    agent_name: str
    input_ref: str | None
    output_ref: str | None
    latency_ms: float | None
    status: str
    started_at: str
    completed_at: str | None


@dataclass(frozen=True, slots=True)
class AgentMessageRecord:
    message_id: str
    agent_run_id: str
    role: str
    payload_json: Mapping[str, Any]
    created_at: str


@dataclass(frozen=True, slots=True)
class ReplayGraphNode:
    node_id: str
    node_type: str
    label: str
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ReplayGraphEdge:
    from_node_id: str
    to_node_id: str
    relation: str


@dataclass(frozen=True, slots=True)
class DecisionReplayResult:
    decision_id: str
    trace_id: str
    strategy_id: str
    mode: str
    status: str
    summary: Mapping[str, Any]
    lifecycle: tuple[Mapping[str, Any], ...]
    agent_runs: tuple[Mapping[str, Any], ...]
    llm_calls: tuple[Mapping[str, Any], ...]
    graph_nodes: tuple[ReplayGraphNode, ...]
    graph_edges: tuple[ReplayGraphEdge, ...]
    deterministic_digest: str
    diff: Mapping[str, Any] | None = None


class ReplayTraceStore(Protocol):
    async def read_decision_trace(self, *, decision_id: str) -> DecisionTraceRecord | None: ...

    async def list_agent_runs(self, *, decision_id: str) -> Sequence[AgentRunRecord]: ...

    async def list_agent_messages(self, *, agent_run_id: str) -> Sequence[AgentMessageRecord]: ...

    async def list_llm_calls(self, *, decision_id: str) -> Sequence[LLMCallRecord]: ...


class DecisionReplayNotFoundError(LookupError):
    """Raised when the replay service cannot locate a requested decision trace."""


class DecisionReplayService:
    def __init__(
        self,
        *,
        trace_store: ReplayTraceStore,
        long_term_store: LongTermMemoryStore | None = None,
    ) -> None:
        self.trace_store = trace_store
        self.long_term_store = long_term_store

    async def replay_decision(self, *, decision_id: str) -> DecisionReplayResult:
        trace = await self.trace_store.read_decision_trace(decision_id=decision_id)
        if trace is None:
            raise DecisionReplayNotFoundError(f"Decision trace not found: {decision_id}")

        summary: Mapping[str, Any] = {}
        lifecycle: tuple[Mapping[str, Any], ...] = ()
        if self.long_term_store is not None:
            archived = await self.long_term_store.read_decision_summary(decision_id=decision_id)
            if archived is not None:
                summary = _ensure_mapping(archived.summary)
                lifecycle = tuple(_ensure_mapping(item) for item in archived.lifecycle)

        decision_node_id = f"decision:{trace.decision_id}"
        graph_nodes: list[ReplayGraphNode] = [
            ReplayGraphNode(
                node_id=decision_node_id,
                node_type="decision_trace",
                label=f"Decision {trace.decision_id}",
                payload={
                    "decision_id": trace.decision_id,
                    "trace_id": trace.trace_id,
                    "strategy_id": trace.strategy_id,
                    "mode": trace.mode,
                    "status": trace.status,
                    "started_at": trace.started_at,
                    "completed_at": trace.completed_at,
                },
            )
        ]
        graph_edges: list[ReplayGraphEdge] = []

        if summary:
            summary_node_id = f"memory:{trace.decision_id}"
            graph_nodes.append(
                ReplayGraphNode(
                    node_id=summary_node_id,
                    node_type="memory_summary",
                    label="Long-term summary",
                    payload=_ensure_mapping(summary),
                )
            )
            graph_edges.append(
                ReplayGraphEdge(
                    from_node_id=decision_node_id,
                    to_node_id=summary_node_id,
                    relation="has_summary",
                )
            )

        runs_payload: list[Mapping[str, Any]] = []
        runs = sorted(
            await self.trace_store.list_agent_runs(decision_id=decision_id), key=_run_sort_key
        )
        for run in runs:
            messages = sorted(
                await self.trace_store.list_agent_messages(agent_run_id=run.agent_run_id),
                key=_message_sort_key,
            )
            message_payload = tuple(_agent_message_payload(item) for item in messages)
            run_payload = {
                "agent_run_id": run.agent_run_id,
                "decision_id": run.decision_id,
                "agent_name": run.agent_name,
                "input_ref": run.input_ref,
                "output_ref": run.output_ref,
                "latency_ms": run.latency_ms,
                "status": run.status,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "messages": [dict(item) for item in message_payload],
            }
            runs_payload.append(run_payload)

            run_node_id = f"agent_run:{run.agent_run_id}"
            graph_nodes.append(
                ReplayGraphNode(
                    node_id=run_node_id,
                    node_type="agent_run",
                    label=run.agent_name,
                    payload={
                        "agent_run_id": run.agent_run_id,
                        "agent_name": run.agent_name,
                        "status": run.status,
                        "started_at": run.started_at,
                        "completed_at": run.completed_at,
                    },
                )
            )
            graph_edges.append(
                ReplayGraphEdge(
                    from_node_id=decision_node_id,
                    to_node_id=run_node_id,
                    relation="has_run",
                )
            )

        llm_payload: list[Mapping[str, Any]] = []
        llm_calls = sorted(
            await self.trace_store.list_llm_calls(decision_id=decision_id),
            key=_llm_call_sort_key,
        )
        for call in llm_calls:
            payload = _llm_call_payload(call)
            llm_payload.append(payload)

            llm_node_id = f"llm_call:{call.llm_call_id}"
            graph_nodes.append(
                ReplayGraphNode(
                    node_id=llm_node_id,
                    node_type="llm_call",
                    label=call.agent_name,
                    payload=payload,
                )
            )
            graph_edges.append(
                ReplayGraphEdge(
                    from_node_id=decision_node_id,
                    to_node_id=llm_node_id,
                    relation="has_llm_call",
                )
            )

        replay_payload = {
            "decision": {
                "decision_id": trace.decision_id,
                "trace_id": trace.trace_id,
                "strategy_id": trace.strategy_id,
                "mode": trace.mode,
                "status": trace.status,
                "started_at": trace.started_at,
                "completed_at": trace.completed_at,
            },
            "summary": _ensure_mapping(summary),
            "lifecycle": [dict(item) for item in lifecycle],
            "agent_runs": [dict(item) for item in runs_payload],
            "llm_calls": [dict(item) for item in llm_payload],
            "graph_nodes": [asdict(item) for item in graph_nodes],
            "graph_edges": [asdict(item) for item in graph_edges],
        }
        digest = _stable_digest(replay_payload)

        # Compare original trace with reconstructed replay
        diff = _compute_replay_diff(
            original_status=trace.status,
            original_summary=_ensure_mapping(summary),
            replay_runs=runs_payload,
            replay_llm_calls=llm_payload,
        )

        return DecisionReplayResult(
            decision_id=trace.decision_id,
            trace_id=trace.trace_id,
            strategy_id=trace.strategy_id,
            mode=trace.mode,
            status=trace.status,
            summary=_ensure_mapping(summary),
            lifecycle=lifecycle,
            agent_runs=tuple(runs_payload),
            llm_calls=tuple(llm_payload),
            graph_nodes=tuple(graph_nodes),
            graph_edges=tuple(graph_edges),
            deterministic_digest=digest,
            diff=diff,
        )


def _stable_digest(value: Mapping[str, Any]) -> str:
    normalized = _normalize(value)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(encoded.encode("ascii")).hexdigest()


def _compute_replay_diff(
    *,
    original_status: str,
    original_summary: Mapping[str, Any],
    replay_runs: list[Mapping[str, Any]],
    replay_llm_calls: list[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    """Compare original trace with reconstructed replay. Returns diff or None if identical."""
    issues: list[str] = []

    # Check for failed agent runs
    failed_runs = [r for r in replay_runs if r.get("status") == "failed"]
    if failed_runs:
        issues.append(f"{len(failed_runs)} agent run(s) failed during replay")

    # Check for missing agent runs
    if not replay_runs:
        issues.append("No agent runs found in replay trace")

    # Check for LLM calls with errors
    error_calls = [c for c in replay_llm_calls if c.get("status") == "error"]
    if error_calls:
        issues.append(f"{len(error_calls)} LLM call(s) errored during original execution")

    # Check decision status consistency
    if original_status == "failed" and not failed_runs and not error_calls:
        issues.append("Original decision failed but replay found no failures")

    if not issues:
        return None

    return {
        "has_differences": True,
        "issues": issues,
        "original_status": original_status,
        "replay_run_count": len(replay_runs),
        "replay_llm_call_count": len(replay_llm_calls),
        "failed_run_count": len(failed_runs),
        "error_call_count": len(error_calls),
    }


def _run_sort_key(record: AgentRunRecord) -> tuple[str, str, str]:
    return (record.started_at or "", record.agent_name, record.agent_run_id)


def _message_sort_key(record: AgentMessageRecord) -> tuple[str, str]:
    return (record.created_at or "", record.message_id)


def _llm_call_sort_key(record: LLMCallRecord) -> tuple[str, str]:
    return (record.created_at or "", record.llm_call_id)


def _agent_message_payload(record: AgentMessageRecord) -> Mapping[str, Any]:
    return {
        "message_id": record.message_id,
        "agent_run_id": record.agent_run_id,
        "role": record.role,
        "payload_json": _ensure_mapping(record.payload_json),
        "created_at": record.created_at,
    }


def _llm_call_payload(record: LLMCallRecord) -> Mapping[str, Any]:
    return {
        "llm_call_id": record.llm_call_id,
        "trace_id": record.trace_id,
        "decision_id": record.decision_id,
        "strategy_id": record.strategy_id,
        "agent_name": record.agent_name,
        "provider": record.provider,
        "model": record.model,
        "prompt_payload": _ensure_mapping(record.prompt_payload),
        "response_payload": _ensure_mapping(record.response_payload),
        "prompt_tokens": record.prompt_tokens,
        "completion_tokens": record.completion_tokens,
        "total_tokens": record.total_tokens,
        "latency_ms": record.latency_ms,
        "estimated_cost": record.estimated_cost,
        "created_at": record.created_at,
    }


def _ensure_mapping(value: Mapping[str, Any] | Any) -> dict[str, Any]:
    normalized = _normalize(value)
    if isinstance(normalized, dict):
        return normalized
    return {"value": normalized}


def _normalize(value: Any) -> Any:
    if is_dataclass(value):
        return _normalize(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value
