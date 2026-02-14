from __future__ import annotations

from typing import Any, Mapping
import asyncio

import pytest

from services.agent_orchestrator.metrics_tracing import AgentRuntimeMetrics
from services.llm_gateway.contracts import (
    GatewaySettings,
    LLMRequest,
    LLMRetryExhaustedError,
    ProviderSettings,
)
from services.llm_gateway.gateway import LLMGateway


class _FlakyProvider:
    def __init__(self, *, fail_attempts: int = 0, delay_seconds: float = 0.0) -> None:
        self.fail_attempts = fail_attempts
        self.delay_seconds = delay_seconds
        self.calls = 0

    async def complete(
        self,
        *,
        model: str,
        messages: tuple[Mapping[str, Any], ...],
        request_kwargs: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.calls += 1
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        if self.calls <= self.fail_attempts:
            raise RuntimeError("transient provider failure")
        return {
            "content": f"response-from-{model}",
            "usage": {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19},
        }


def _request() -> LLMRequest:
    return LLMRequest(
        trace_id="72e328e6-e346-4a59-896b-6d6afe8f8e7c",
        decision_id="39675d5a-c8eb-4292-a36e-c3d8fd8e7f1f",
        strategy_id="scalp-long-short",
        agent_name="planner",
        messages=({"role": "system", "content": "be concise"}, {"role": "user", "content": "plan"}),
        temperature=0.2,
        max_tokens=256,
        metadata={"symbol": "BTC/USDT"},
    )


def _settings() -> GatewaySettings:
    return GatewaySettings(
        providers={
            "primary": ProviderSettings(alias="primary", model="gpt-4o-mini", timeout_ms=40, max_retries=1),
            "secondary": ProviderSettings(
                alias="secondary", model="gpt-4o-mini", timeout_ms=40, max_retries=0
            ),
        },
        default_provider_order=("primary", "secondary"),
        retry_base_ms=1,
        retry_max_ms=2,
    )


@pytest.mark.asyncio
async def test_gateway_returns_primary_provider_response() -> None:
    gateway = LLMGateway(settings=_settings(), provider_clients={"primary": _FlakyProvider()})

    response = await gateway.generate(_request(), provider_order=("primary",))

    assert response.provider == "primary"
    assert response.model == "gpt-4o-mini"
    assert response.content.startswith("response-from")
    assert response.attempt_count == 1
    assert response.usage["total_tokens"] == 19


@pytest.mark.asyncio
async def test_gateway_retries_transient_provider_failure_then_succeeds() -> None:
    provider = _FlakyProvider(fail_attempts=1)
    gateway = LLMGateway(settings=_settings(), provider_clients={"primary": provider})

    response = await gateway.generate(_request(), provider_order=("primary",))

    assert response.provider == "primary"
    assert response.attempt_count == 2
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_gateway_falls_back_to_secondary_provider_after_primary_exhausted() -> None:
    primary = _FlakyProvider(fail_attempts=5)
    secondary = _FlakyProvider()
    gateway = LLMGateway(
        settings=_settings(),
        provider_clients={"primary": primary, "secondary": secondary},
    )

    response = await gateway.generate(_request())

    assert response.provider == "secondary"
    assert response.attempt_count == 1
    assert primary.calls == 2
    assert secondary.calls == 1


@pytest.mark.asyncio
async def test_gateway_handles_timeout_then_fallback() -> None:
    slow = _FlakyProvider(delay_seconds=0.08)
    fast = _FlakyProvider()
    gateway = LLMGateway(
        settings=_settings(),
        provider_clients={"primary": slow, "secondary": fast},
    )

    response = await gateway.generate(_request())

    assert response.provider == "secondary"
    assert slow.calls == 2
    assert fast.calls == 1


@pytest.mark.asyncio
async def test_gateway_raises_when_all_providers_fail() -> None:
    primary = _FlakyProvider(fail_attempts=5)
    secondary = _FlakyProvider(fail_attempts=5)
    gateway = LLMGateway(
        settings=_settings(),
        provider_clients={"primary": primary, "secondary": secondary},
    )

    with pytest.raises(LLMRetryExhaustedError):
        await gateway.generate(_request())


@pytest.mark.asyncio
async def test_gateway_records_token_consumption_metrics_when_enabled() -> None:
    metrics = AgentRuntimeMetrics()
    gateway = LLMGateway(
        settings=_settings(),
        provider_clients={"primary": _FlakyProvider()},
        metrics=metrics,
    )

    await gateway.generate(_request(), provider_order=("primary",))
    snapshot = metrics.snapshot()

    totals = snapshot["llm_usage"]["totals"]
    assert totals["calls_total"] == 1
    assert totals["tokens_total"] == 19
    assert totals["failed_calls_total"] == 0
    scoped = snapshot["llm_usage"]["by_scope"]["scalp-long-short:planner"]
    assert scoped["tokens_total"] == 19
