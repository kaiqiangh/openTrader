from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class DecisionMemoryRecord:
    trace_id: str
    decision_id: str
    strategy_id: str
    mode: str
    status: str
    summary: Mapping[str, Any]
    lifecycle: tuple[Mapping[str, Any], ...]
    persisted_at: str


@dataclass(frozen=True, slots=True)
class DecisionMemorySnapshot:
    mode: str
    strategy_id: str
    decision_id: str
    source: str
    slots: Mapping[str, Mapping[str, Any]]


class ShortTermMemoryStore(Protocol):
    async def write_slot(
        self,
        *,
        mode: str,
        strategy_id: str,
        decision_id: str,
        slot: str,
        payload: Mapping[str, Any],
        ttl_seconds: int,
    ) -> None: ...

    async def read_slots(
        self,
        *,
        mode: str,
        strategy_id: str,
        decision_id: str,
    ) -> Mapping[str, Mapping[str, Any]]: ...


class LongTermMemoryStore(Protocol):
    async def persist_decision_summary(self, record: DecisionMemoryRecord) -> None: ...

    async def read_decision_summary(self, *, decision_id: str) -> DecisionMemoryRecord | None: ...


class _NoopShortTermMemoryStore:
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
        return None

    async def read_slots(
        self,
        *,
        mode: str,
        strategy_id: str,
        decision_id: str,
    ) -> Mapping[str, Mapping[str, Any]]:
        return {}


class _NoopLongTermMemoryStore:
    async def persist_decision_summary(self, record: DecisionMemoryRecord) -> None:
        return None

    async def read_decision_summary(self, *, decision_id: str) -> DecisionMemoryRecord | None:
        return None


class AgentMemoryLayer:
    def __init__(
        self,
        *,
        short_term_store: ShortTermMemoryStore | None = None,
        long_term_store: LongTermMemoryStore | None = None,
        decision_ttl_seconds: int = 900,
    ) -> None:
        self.short_term_store = short_term_store or _NoopShortTermMemoryStore()
        self.long_term_store = long_term_store or _NoopLongTermMemoryStore()
        self.decision_ttl_seconds = decision_ttl_seconds

    async def read_decision_memory(
        self,
        *,
        mode: str,
        strategy_id: str,
        decision_id: str,
    ) -> DecisionMemorySnapshot:
        slots = await self.short_term_store.read_slots(
            mode=mode,
            strategy_id=strategy_id,
            decision_id=decision_id,
        )
        normalized_slots = {slot: _ensure_mapping(payload) for slot, payload in slots.items()}
        if normalized_slots:
            return DecisionMemorySnapshot(
                mode=mode,
                strategy_id=strategy_id,
                decision_id=decision_id,
                source="redis",
                slots=normalized_slots,
            )

        archived = await self.long_term_store.read_decision_summary(decision_id=decision_id)
        if archived is None:
            return DecisionMemorySnapshot(
                mode=mode,
                strategy_id=strategy_id,
                decision_id=decision_id,
                source="empty",
                slots={},
            )

        summary_payload = _ensure_mapping(archived.summary)
        await self.short_term_store.write_slot(
            mode=mode,
            strategy_id=strategy_id,
            decision_id=decision_id,
            slot="summary",
            payload=summary_payload,
            ttl_seconds=self.decision_ttl_seconds,
        )
        return DecisionMemorySnapshot(
            mode=mode,
            strategy_id=strategy_id,
            decision_id=decision_id,
            source="postgres",
            slots={"summary": summary_payload},
        )

    async def write_decision_slot(
        self,
        *,
        mode: str,
        strategy_id: str,
        decision_id: str,
        slot: str,
        payload: Mapping[str, Any],
    ) -> None:
        await self.short_term_store.write_slot(
            mode=mode,
            strategy_id=strategy_id,
            decision_id=decision_id,
            slot=slot,
            payload=_ensure_mapping(payload),
            ttl_seconds=self.decision_ttl_seconds,
        )

    async def persist_decision_summary(
        self,
        *,
        trace_id: str,
        decision_id: str,
        strategy_id: str,
        mode: str,
        status: str,
        market_context: Mapping[str, Any],
        plan: Mapping[str, Any],
        risk: Mapping[str, Any],
        execution_decision: Mapping[str, Any],
        guardrail: Mapping[str, Any],
        lifecycle: tuple[Mapping[str, Any], ...],
    ) -> DecisionMemoryRecord:
        summary = {
            "status": status,
            "market_context": _ensure_mapping(market_context),
            "plan": _ensure_mapping(plan),
            "risk": _ensure_mapping(risk),
            "execution_decision": _ensure_mapping(execution_decision),
            "guardrail": _ensure_mapping(guardrail),
        }
        record = DecisionMemoryRecord(
            trace_id=trace_id,
            decision_id=decision_id,
            strategy_id=strategy_id,
            mode=mode,
            status=status,
            summary=summary,
            lifecycle=tuple(_ensure_mapping(item) for item in lifecycle),
            persisted_at=_utc_now_iso(),
        )
        await self.long_term_store.persist_decision_summary(record)
        await self.short_term_store.write_slot(
            mode=mode,
            strategy_id=strategy_id,
            decision_id=decision_id,
            slot="summary",
            payload=summary,
            ttl_seconds=self.decision_ttl_seconds,
        )
        return record


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
