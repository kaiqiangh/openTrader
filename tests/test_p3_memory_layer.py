from __future__ import annotations

from typing import Any, Mapping

import pytest

from services.agent_orchestrator.memory_layer import AgentMemoryLayer, DecisionMemoryRecord


class _FakeRedisMemoryStore:
    def __init__(self) -> None:
        self.slots: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        self.write_calls: list[dict[str, Any]] = []

    async def write_slot(
        self,
        *,
        mode: str,
        strategy_id: str,
        decision_id: str,
        slot: str,
        payload: Mapping[str, Any],
        ttl_seconds: int,
    ) -> None:
        self.slots[(mode, strategy_id, decision_id, slot)] = dict(payload)
        self.write_calls.append(
            {
                "mode": mode,
                "strategy_id": strategy_id,
                "decision_id": decision_id,
                "slot": slot,
                "ttl_seconds": ttl_seconds,
            }
        )

    async def read_slots(
        self,
        *,
        mode: str,
        strategy_id: str,
        decision_id: str,
    ) -> Mapping[str, Mapping[str, Any]]:
        result: dict[str, Mapping[str, Any]] = {}
        for (entry_mode, entry_strategy, entry_decision, slot), payload in self.slots.items():
            if (entry_mode, entry_strategy, entry_decision) == (mode, strategy_id, decision_id):
                result[slot] = payload
        return result


class _FakePostgresMemoryStore:
    def __init__(self) -> None:
        self.records: dict[str, DecisionMemoryRecord] = {}

    async def persist_decision_summary(self, record: DecisionMemoryRecord) -> None:
        self.records[record.decision_id] = record

    async def read_decision_summary(self, *, decision_id: str) -> DecisionMemoryRecord | None:
        return self.records.get(decision_id)


@pytest.mark.asyncio
async def test_memory_layer_writes_and_reads_short_term_slots() -> None:
    redis_store = _FakeRedisMemoryStore()
    postgres_store = _FakePostgresMemoryStore()
    layer = AgentMemoryLayer(short_term_store=redis_store, long_term_store=postgres_store)

    await layer.write_decision_slot(
        mode="MOCK",
        strategy_id="strategy-1",
        decision_id="decision-1",
        slot="plan",
        payload={"action": "BUY", "confidence": 0.91},
    )

    snapshot = await layer.read_decision_memory(
        mode="MOCK",
        strategy_id="strategy-1",
        decision_id="decision-1",
    )

    assert snapshot.source == "redis"
    assert snapshot.slots["plan"]["action"] == "BUY"
    assert redis_store.write_calls[0]["ttl_seconds"] == 900


@pytest.mark.asyncio
async def test_memory_layer_falls_back_to_long_term_and_rehydrates_short_term() -> None:
    redis_store = _FakeRedisMemoryStore()
    postgres_store = _FakePostgresMemoryStore()
    layer = AgentMemoryLayer(short_term_store=redis_store, long_term_store=postgres_store)

    await postgres_store.persist_decision_summary(
        DecisionMemoryRecord(
            trace_id="trace-1",
            decision_id="decision-2",
            strategy_id="strategy-2",
            mode="REAL",
            status="RISK_APPROVED",
            summary={"status": "RISK_APPROVED", "action": "BUY"},
            lifecycle=({"event_type": "agent.decision.planned"},),
            persisted_at="2026-02-14T14:56:00Z",
        )
    )

    snapshot = await layer.read_decision_memory(
        mode="REAL",
        strategy_id="strategy-2",
        decision_id="decision-2",
    )

    assert snapshot.source == "postgres"
    assert snapshot.slots["summary"]["status"] == "RISK_APPROVED"
    assert any(call["slot"] == "summary" for call in redis_store.write_calls)


@pytest.mark.asyncio
async def test_memory_layer_persists_long_term_summary() -> None:
    redis_store = _FakeRedisMemoryStore()
    postgres_store = _FakePostgresMemoryStore()
    layer = AgentMemoryLayer(short_term_store=redis_store, long_term_store=postgres_store)

    record = await layer.persist_decision_summary(
        trace_id="trace-3",
        decision_id="decision-3",
        strategy_id="strategy-3",
        mode="MOCK",
        status="RISK_APPROVED",
        market_context={"symbol": "BTC/USDT", "mid_price": 42_000.5},
        plan={"action": "BUY", "target_quantity": 0.1},
        risk={"approved": True, "risk_score": 0.94},
        execution_decision={"action": "BUY", "quantity": 0.1},
        guardrail={"allowed": True, "blocked_by": []},
        lifecycle=(
            {"event_type": "agent.decision.received"},
            {"event_type": "agent.decision.intent_published"},
        ),
    )

    assert record.status == "RISK_APPROVED"
    stored = postgres_store.records["decision-3"]
    assert stored.summary["execution_decision"]["action"] == "BUY"
    assert stored.summary["guardrail"]["allowed"] is True
