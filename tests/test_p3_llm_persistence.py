from __future__ import annotations

from typing import Any, Mapping

import pytest

from services.llm_gateway.contracts import (
    GatewaySettings,
    LLMRequest,
    LLMRetryExhaustedError,
    ProviderSettings,
)
from services.llm_gateway.gateway import LLMGateway
from services.llm_gateway.persistence import LLMCallRecord


class _MemoryCallStore:
    def __init__(self) -> None:
        self.records: list[LLMCallRecord] = []

    async def persist_call(self, record: LLMCallRecord) -> None:
        self.records.append(record)


class _FailingProvider:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls = 0

    async def complete(
        self,
        *,
        model: str,
        messages: tuple[Mapping[str, Any], ...],
        request_kwargs: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.calls += 1
        if self.should_fail:
            raise RuntimeError("provider unavailable")
        return {
            "content": "gateway-persisted-response",
            "usage": {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200},
            "raw": {"model": model},
        }


def _settings() -> GatewaySettings:
    return GatewaySettings(
        providers={
            "primary": ProviderSettings(
                alias="primary",
                model="gpt-4o-mini",
                timeout_ms=100,
                max_retries=1,
                prompt_cost_per_1k_tokens=0.003,
                completion_cost_per_1k_tokens=0.006,
            )
        },
        default_provider_order=("primary",),
        retry_base_ms=1,
        retry_max_ms=2,
    )


def _request() -> LLMRequest:
    return LLMRequest(
        trace_id="31bcd0af-c24d-4720-aee2-8b67cfe0532c",
        decision_id="44453fa2-bfdb-4bc8-a57f-d2904e5d364d",
        strategy_id="37e4f4b8-7231-4817-a0e2-2ce9fca4c3ef",
        agent_name="planner",
        messages=(
            {"role": "system", "content": "respond in json"},
            {"role": "user", "content": "summarize risk"},
        ),
        temperature=0.2,
        max_tokens=256,
        metadata={"symbol": "BTC/USDT"},
    )


@pytest.mark.asyncio
async def test_gateway_persists_successful_prompt_and_response_payloads() -> None:
    store = _MemoryCallStore()
    gateway = LLMGateway(
        settings=_settings(),
        provider_clients={"primary": _FailingProvider(should_fail=False)},
        call_store=store,
    )

    response = await gateway.generate(_request())

    assert response.provider == "primary"
    assert len(store.records) == 1
    record = store.records[0]
    assert record.trace_id == "31bcd0af-c24d-4720-aee2-8b67cfe0532c"
    assert record.decision_id == "44453fa2-bfdb-4bc8-a57f-d2904e5d364d"
    assert record.agent_name == "planner"
    assert record.prompt_payload["messages"][0]["role"] == "system"
    assert record.response_payload["status"] == "succeeded"
    assert record.prompt_tokens == 120
    assert record.completion_tokens == 80
    assert record.total_tokens == 200
    assert record.estimated_cost > 0
    assert record.latency_ms >= 0


@pytest.mark.asyncio
async def test_gateway_persists_failure_record_when_all_providers_exhausted() -> None:
    store = _MemoryCallStore()
    gateway = LLMGateway(
        settings=_settings(),
        provider_clients={"primary": _FailingProvider(should_fail=True)},
        call_store=store,
    )

    with pytest.raises(LLMRetryExhaustedError):
        await gateway.generate(_request())

    assert len(store.records) == 1
    record = store.records[0]
    assert record.response_payload["status"] == "failed"
    assert record.response_payload["provider_errors"]
    assert record.prompt_tokens == 0
    assert record.completion_tokens == 0
    assert record.total_tokens == 0
    assert record.estimated_cost == 0.0
