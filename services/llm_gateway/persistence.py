from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class LLMCallRecord:
    llm_call_id: str
    trace_id: str
    decision_id: str
    strategy_id: str
    agent_name: str
    provider: str
    model: str
    prompt_payload: Mapping[str, Any]
    response_payload: Mapping[str, Any]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    estimated_cost: float
    created_at: str


class LLMCallStore(Protocol):
    async def persist_call(self, record: LLMCallRecord) -> None: ...
