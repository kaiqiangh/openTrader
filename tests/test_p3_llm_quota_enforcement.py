from __future__ import annotations

from typing import Any, Mapping

import pytest

from services.llm_gateway.contracts import (
    GatewaySettings,
    LLMQuotaExceededError,
    LLMRequest,
    ProviderSettings,
)
from services.llm_gateway.gateway import LLMGateway
from services.llm_gateway.persistence import LLMCallRecord
from services.llm_gateway.quota import QuotaLimits, QuotaUsage


class _MemoryQuotaStore:
    def __init__(self, *, limits: QuotaLimits, usage: QuotaUsage) -> None:
        self.limits = limits
        self.usage = usage
        self.increment_calls = 0

    async def get_limits(self, *, strategy_id: str, agent_name: str) -> QuotaLimits:
        return self.limits

    async def get_usage(self, *, strategy_id: str, agent_name: str) -> QuotaUsage:
        return self.usage

    async def increment_usage(
        self,
        *,
        strategy_id: str,
        agent_name: str,
        added_tokens: int,
        added_cost: float,
    ) -> QuotaUsage:
        self.increment_calls += 1
        self.usage = QuotaUsage(
            daily_tokens=self.usage.daily_tokens + added_tokens,
            monthly_cost=self.usage.monthly_cost + added_cost,
        )
        return self.usage


class _MemoryCallStore:
    def __init__(self) -> None:
        self.records: list[LLMCallRecord] = []

    async def persist_call(self, record: LLMCallRecord) -> None:
        self.records.append(record)


class _Provider:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(
        self,
        *,
        model: str,
        messages: tuple[Mapping[str, Any], ...],
        request_kwargs: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.calls += 1
        return {
            "content": "ok",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }


def _request() -> LLMRequest:
    return LLMRequest(
        trace_id="3a5f34d6-0eb6-4f4f-9389-727cdeff7f4c",
        decision_id="66d2d9e4-72c1-4f9f-b58f-77f15a04f93e",
        strategy_id="d17ea0d5-3fd3-42e4-92b4-f4d34f88af0e",
        agent_name="planner",
        messages=({"role": "system", "content": "stay concise"}, {"role": "user", "content": "analyze"}),
        temperature=0.2,
        max_tokens=120,
        metadata={"symbol": "BTC/USDT"},
    )


def _settings() -> GatewaySettings:
    return GatewaySettings(
        providers={
            "primary": ProviderSettings(
                alias="primary",
                model="gpt-4o-mini",
                timeout_ms=100,
                max_retries=0,
                prompt_cost_per_1k_tokens=0.002,
                completion_cost_per_1k_tokens=0.004,
            )
        },
        default_provider_order=("primary",),
        retry_base_ms=1,
        retry_max_ms=2,
    )


@pytest.mark.asyncio
async def test_gateway_increments_quota_usage_on_success() -> None:
    quota_store = _MemoryQuotaStore(
        limits=QuotaLimits(daily_token_limit=10_000, monthly_cost_limit=200.0, is_hard_limit=True),
        usage=QuotaUsage(daily_tokens=100, monthly_cost=1.0),
    )
    provider = _Provider()
    gateway = LLMGateway(
        settings=_settings(),
        provider_clients={"primary": provider},
        quota_store=quota_store,
    )

    response = await gateway.generate(_request())

    assert response.provider == "primary"
    assert quota_store.increment_calls == 1
    assert quota_store.usage.daily_tokens == 250
    assert quota_store.usage.monthly_cost > 1.0


@pytest.mark.asyncio
async def test_gateway_blocks_when_daily_token_limit_exceeded() -> None:
    quota_store = _MemoryQuotaStore(
        limits=QuotaLimits(daily_token_limit=150, monthly_cost_limit=200.0, is_hard_limit=True),
        usage=QuotaUsage(daily_tokens=145, monthly_cost=0.0),
    )
    provider = _Provider()
    gateway = LLMGateway(
        settings=_settings(),
        provider_clients={"primary": provider},
        quota_store=quota_store,
    )

    with pytest.raises(LLMQuotaExceededError):
        await gateway.generate(_request())

    assert provider.calls == 0
    assert quota_store.increment_calls == 0


@pytest.mark.asyncio
async def test_gateway_blocks_when_monthly_cost_limit_exceeded() -> None:
    quota_store = _MemoryQuotaStore(
        limits=QuotaLimits(daily_token_limit=10_000, monthly_cost_limit=0.0004, is_hard_limit=True),
        usage=QuotaUsage(daily_tokens=0, monthly_cost=0.0),
    )
    provider = _Provider()
    gateway = LLMGateway(
        settings=_settings(),
        provider_clients={"primary": provider},
        quota_store=quota_store,
    )

    with pytest.raises(LLMQuotaExceededError):
        await gateway.generate(_request())

    assert provider.calls == 0
    assert quota_store.increment_calls == 0


@pytest.mark.asyncio
async def test_gateway_persists_quota_block_record() -> None:
    quota_store = _MemoryQuotaStore(
        limits=QuotaLimits(daily_token_limit=150, monthly_cost_limit=200.0, is_hard_limit=True),
        usage=QuotaUsage(daily_tokens=145, monthly_cost=0.0),
    )
    call_store = _MemoryCallStore()
    gateway = LLMGateway(
        settings=_settings(),
        provider_clients={"primary": _Provider()},
        quota_store=quota_store,
        call_store=call_store,
    )

    with pytest.raises(LLMQuotaExceededError):
        await gateway.generate(_request())

    assert len(call_store.records) == 1
    assert call_store.records[0].response_payload["status"] == "quota_blocked"
