from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol
import asyncio
import logging
import time
import uuid

logger = logging.getLogger(__name__)

from services.llm_gateway.contracts import (
    GatewaySettings,
    LLMMetricsSink,
    LLMQuotaExceededError,
    LLMRequest,
    LLMResponse,
    LLMRetryExhaustedError,
    ProviderNotConfiguredError,
    ProviderSettings,
)
from services.llm_gateway.persistence import LLMCallRecord, LLMCallStore
from services.llm_gateway.quota import LLMQuotaStore


class LLMProviderClient(Protocol):
    async def complete(
        self,
        *,
        model: str,
        messages: tuple[Mapping[str, Any], ...],
        request_kwargs: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class LLMGateway:
    def __init__(
        self,
        *,
        settings: GatewaySettings,
        provider_clients: Mapping[str, LLMProviderClient],
        call_store: LLMCallStore | None = None,
        quota_store: LLMQuotaStore | None = None,
        metrics: LLMMetricsSink | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic_clock: Callable[[], float] = time.monotonic,
        uuid_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
        now_factory: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.settings = settings
        self.provider_clients = dict(provider_clients)
        self.call_store = call_store
        self.quota_store = quota_store
        self.metrics = metrics
        self._sleep = sleep
        self._monotonic_clock = monotonic_clock
        self._uuid_factory = uuid_factory
        self._now_factory = now_factory

    async def generate(
        self,
        request: LLMRequest,
        *,
        provider_order: Sequence[str] | None = None,
    ) -> LLMResponse:
        ordered_aliases = tuple(provider_order or self.settings.default_provider_order)
        if not ordered_aliases:
            raise LLMRetryExhaustedError("No provider aliases configured for gateway request")
        await self._enforce_hard_quota_limits(request=request, ordered_aliases=ordered_aliases)

        error_summaries: list[str] = []
        last_provider_alias: str | None = None
        last_provider_model: str | None = None
        for alias in ordered_aliases:
            provider = self._get_provider(alias)
            if not provider.enabled:
                error_summaries.append(f"{alias}: provider_disabled")
                continue
            last_provider_alias = alias
            last_provider_model = provider.model

            client = self.provider_clients.get(alias)
            if client is None:
                raise ProviderNotConfiguredError(f"Provider client not configured: {alias}")

            for attempt_idx in range(provider.max_retries + 1):
                started = self._monotonic_clock()
                try:
                    raw_payload = await asyncio.wait_for(
                        client.complete(
                            model=provider.model,
                            messages=request.messages,
                            request_kwargs=self._request_kwargs(request, provider),
                        ),
                        timeout=max(provider.timeout_ms, 1) / 1000.0,
                    )
                    latency_ms = int((self._monotonic_clock() - started) * 1000.0)
                    response = LLMResponse(
                        provider=alias,
                        model=provider.model,
                        content=self._extract_content(raw_payload),
                        raw_payload=raw_payload,
                        usage=self._extract_usage(raw_payload),
                        latency_ms=max(latency_ms, 0),
                        attempt_count=attempt_idx + 1,
                    )
                    estimated_cost = self._estimate_cost(
                        prompt_tokens=response.usage["prompt_tokens"],
                        completion_tokens=response.usage["completion_tokens"],
                        provider=provider,
                    )
                    await self._increment_quota_usage(
                        request=request,
                        added_tokens=response.usage["total_tokens"],
                        added_cost=estimated_cost,
                    )
                    await self._persist_success_record(
                        request=request,
                        provider=provider,
                        response=response,
                        estimated_cost=estimated_cost,
                    )
                    self._record_llm_metrics(
                        request=request,
                        provider_alias=alias,
                        model=provider.model,
                        prompt_tokens=response.usage["prompt_tokens"],
                        completion_tokens=response.usage["completion_tokens"],
                        total_tokens=response.usage["total_tokens"],
                        latency_ms=float(response.latency_ms),
                        estimated_cost=estimated_cost,
                        status="succeeded",
                    )
                    return response
                except Exception as exc:  # noqa: BLE001 - gateway intentionally normalizes provider errors
                    reason = exc.__class__.__name__
                    if isinstance(exc, asyncio.TimeoutError):
                        reason = "timeout"
                    error_summaries.append(f"{alias}:attempt{attempt_idx + 1}:{reason}")
                    if attempt_idx < provider.max_retries:
                        await self._sleep(self._retry_delay_seconds(attempt_idx))
                        continue
                    break

        await self._persist_failure_record(
            request=request,
            provider_alias=last_provider_alias or "unknown",
            model=last_provider_model or "unknown",
            error_summaries=tuple(error_summaries),
        )
        self._record_llm_metrics(
            request=request,
            provider_alias=last_provider_alias or "unknown",
            model=last_provider_model or "unknown",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=0.0,
            estimated_cost=0.0,
            status="failed",
        )
        joined = "; ".join(error_summaries) if error_summaries else "unknown_gateway_error"
        raise LLMRetryExhaustedError(f"LLM request failed across configured providers: {joined}")

    def _get_provider(self, alias: str) -> ProviderSettings:
        provider = self.settings.providers.get(alias)
        if provider is None:
            raise ProviderNotConfiguredError(f"Provider settings not found for alias: {alias}")
        return provider

    def _retry_delay_seconds(self, attempt_idx: int) -> float:
        delay_ms = self.settings.retry_base_ms * (2**attempt_idx)
        bounded = min(delay_ms, self.settings.retry_max_ms)
        return max(bounded, 0) / 1000.0

    @staticmethod
    def _request_kwargs(request: LLMRequest, provider: ProviderSettings) -> dict[str, Any]:
        kwargs = {
            "trace_id": request.trace_id,
            "decision_id": request.decision_id,
            "strategy_id": request.strategy_id,
            "agent_name": request.agent_name,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "requested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        kwargs.update(provider.extra)
        kwargs.update(request.metadata)
        return kwargs

    @staticmethod
    def _extract_content(payload: Mapping[str, Any]) -> str:
        if isinstance(payload.get("content"), str):
            return str(payload["content"])

        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, Mapping):
                message = first.get("message")
                if isinstance(message, Mapping) and isinstance(message.get("content"), str):
                    return str(message["content"])
                if isinstance(first.get("text"), str):
                    return str(first["text"])
        return ""

    @staticmethod
    def _extract_usage(payload: Mapping[str, Any]) -> dict[str, int]:
        usage = payload.get("usage")
        if not isinstance(usage, Mapping):
            return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens) or 0)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

    async def _persist_success_record(
        self,
        *,
        request: LLMRequest,
        provider: ProviderSettings,
        response: LLMResponse,
        estimated_cost: float,
    ) -> None:
        if self.call_store is None:
            return

        record = LLMCallRecord(
            llm_call_id=self._uuid_factory(),
            trace_id=request.trace_id,
            decision_id=request.decision_id,
            strategy_id=request.strategy_id,
            agent_name=request.agent_name,
            provider=response.provider,
            model=response.model,
            prompt_payload={
                "messages": [dict(item) for item in request.messages],
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "metadata": dict(request.metadata),
            },
            response_payload={
                "status": "succeeded",
                "content": response.content,
                "raw_payload": dict(response.raw_payload),
                "attempt_count": response.attempt_count,
            },
            prompt_tokens=response.usage["prompt_tokens"],
            completion_tokens=response.usage["completion_tokens"],
            total_tokens=response.usage["total_tokens"],
            latency_ms=float(response.latency_ms),
            estimated_cost=estimated_cost,
            created_at=self._now_factory().isoformat().replace("+00:00", "Z"),
        )
        await self.call_store.persist_call(record)

    async def _persist_failure_record(
        self,
        *,
        request: LLMRequest,
        provider_alias: str,
        model: str,
        error_summaries: tuple[str, ...],
    ) -> None:
        if self.call_store is None:
            return

        record = LLMCallRecord(
            llm_call_id=self._uuid_factory(),
            trace_id=request.trace_id,
            decision_id=request.decision_id,
            strategy_id=request.strategy_id,
            agent_name=request.agent_name,
            provider=provider_alias,
            model=model,
            prompt_payload={
                "messages": [dict(item) for item in request.messages],
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "metadata": dict(request.metadata),
            },
            response_payload={
                "status": "failed",
                "provider_errors": list(error_summaries),
            },
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=0.0,
            estimated_cost=0.0,
            created_at=self._now_factory().isoformat().replace("+00:00", "Z"),
        )
        await self.call_store.persist_call(record)

    async def _persist_quota_block_record(
        self,
        *,
        request: LLMRequest,
        reason: str,
        projected_tokens: int,
        projected_cost: float,
    ) -> None:
        if self.call_store is None:
            return

        record = LLMCallRecord(
            llm_call_id=self._uuid_factory(),
            trace_id=request.trace_id,
            decision_id=request.decision_id,
            strategy_id=request.strategy_id,
            agent_name=request.agent_name,
            provider="quota_guard",
            model="quota_guard",
            prompt_payload={
                "messages": [dict(item) for item in request.messages],
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "metadata": dict(request.metadata),
            },
            response_payload={
                "status": "quota_blocked",
                "reason": reason,
                "projected_tokens": projected_tokens,
                "projected_cost": projected_cost,
            },
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=0.0,
            estimated_cost=0.0,
            created_at=self._now_factory().isoformat().replace("+00:00", "Z"),
        )
        await self.call_store.persist_call(record)

    async def _enforce_hard_quota_limits(
        self,
        *,
        request: LLMRequest,
        ordered_aliases: tuple[str, ...],
    ) -> None:
        if self.quota_store is None:
            return

        limits = await self.quota_store.get_limits(
            strategy_id=request.strategy_id,
            agent_name=request.agent_name,
        )
        if not limits.is_hard_limit:
            return

        usage = await self.quota_store.get_usage(
            strategy_id=request.strategy_id,
            agent_name=request.agent_name,
        )

        projected_prompt_tokens = self._estimate_prompt_tokens(request.messages)
        projected_completion_tokens = max(int(request.max_tokens), 0)
        projected_total_tokens = projected_prompt_tokens + projected_completion_tokens
        projected_daily_total = usage.daily_tokens + projected_total_tokens

        # Soft alerts at 80% and 95% of daily limit
        if limits.daily_token_limit is not None and limits.daily_token_limit > 0:
            utilization = projected_daily_total / limits.daily_token_limit
            if utilization >= 0.95:
                logger.warning(
                    "llm_quota_soft_alert",
                    extra={
                        "utilization": f"{utilization:.0%}",
                        "daily_tokens": projected_daily_total,
                        "daily_limit": limits.daily_token_limit,
                        "strategy_id": request.strategy_id,
                        "agent_name": request.agent_name,
                    },
                )
            elif utilization >= 0.80:
                logger.info(
                    "llm_quota_soft_alert",
                    extra={
                        "utilization": f"{utilization:.0%}",
                        "daily_tokens": projected_daily_total,
                        "daily_limit": limits.daily_token_limit,
                        "strategy_id": request.strategy_id,
                        "agent_name": request.agent_name,
                    },
                )

        if limits.daily_token_limit is not None and projected_daily_total > limits.daily_token_limit:
            reason = "daily_token_limit_exceeded"
            projected_cost = self._minimum_projected_cost(
                ordered_aliases=ordered_aliases,
                projected_prompt_tokens=projected_prompt_tokens,
                projected_completion_tokens=projected_completion_tokens,
            )
            await self._persist_quota_block_record(
                request=request,
                reason=reason,
                projected_tokens=projected_daily_total,
                projected_cost=projected_cost,
            )
            self._record_llm_metrics(
                request=request,
                provider_alias="quota_guard",
                model="quota_guard",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                latency_ms=0.0,
                estimated_cost=0.0,
                status="quota_blocked",
            )
            raise LLMQuotaExceededError(
                f"{reason}: projected={projected_daily_total} limit={limits.daily_token_limit}"
            )

        if limits.monthly_cost_limit is not None:
            projected_cost = self._minimum_projected_cost(
                ordered_aliases=ordered_aliases,
                projected_prompt_tokens=projected_prompt_tokens,
                projected_completion_tokens=projected_completion_tokens,
            )
            projected_monthly_cost = usage.monthly_cost + projected_cost
            if projected_monthly_cost > limits.monthly_cost_limit:
                reason = "monthly_cost_limit_exceeded"
                await self._persist_quota_block_record(
                    request=request,
                    reason=reason,
                    projected_tokens=projected_total_tokens,
                    projected_cost=projected_monthly_cost,
                )
                self._record_llm_metrics(
                    request=request,
                    provider_alias="quota_guard",
                    model="quota_guard",
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    latency_ms=0.0,
                    estimated_cost=0.0,
                    status="quota_blocked",
                )
                raise LLMQuotaExceededError(
                    f"{reason}: projected={projected_monthly_cost:.8f} limit={limits.monthly_cost_limit:.8f}"
                )

    async def _increment_quota_usage(
        self,
        *,
        request: LLMRequest,
        added_tokens: int,
        added_cost: float,
    ) -> None:
        if self.quota_store is None:
            return
        await self.quota_store.increment_usage(
            strategy_id=request.strategy_id,
            agent_name=request.agent_name,
            added_tokens=added_tokens,
            added_cost=added_cost,
        )

    @staticmethod
    def _estimate_prompt_tokens(messages: tuple[Mapping[str, Any], ...]) -> int:
        characters = 0
        for message in messages:
            role = str(message.get("role", ""))
            content = str(message.get("content", ""))
            characters += len(role) + len(content)
        estimated = max(1, characters // 4)
        return estimated

    def _minimum_projected_cost(
        self,
        *,
        ordered_aliases: tuple[str, ...],
        projected_prompt_tokens: int,
        projected_completion_tokens: int,
    ) -> float:
        costs: list[float] = []
        for alias in ordered_aliases:
            provider = self._get_provider(alias)
            if not provider.enabled:
                continue
            costs.append(
                self._estimate_cost(
                    prompt_tokens=projected_prompt_tokens,
                    completion_tokens=projected_completion_tokens,
                    provider=provider,
                )
            )
        if not costs:
            return 0.0
        return min(costs)

    def _record_llm_metrics(
        self,
        *,
        request: LLMRequest,
        provider_alias: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        latency_ms: float,
        estimated_cost: float,
        status: str,
    ) -> None:
        if self.metrics is None:
            return
        self.metrics.record_llm_call(
            trace_id=request.trace_id,
            decision_id=request.decision_id,
            strategy_id=request.strategy_id,
            agent_name=request.agent_name,
            provider=provider_alias,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            estimated_cost=estimated_cost,
            status=status,
        )

    @staticmethod
    def _estimate_cost(
        *,
        prompt_tokens: int,
        completion_tokens: int,
        provider: ProviderSettings,
    ) -> float:
        prompt_cost = (prompt_tokens / 1000.0) * provider.prompt_cost_per_1k_tokens
        completion_cost = (completion_tokens / 1000.0) * provider.completion_cost_per_1k_tokens
        return round(prompt_cost + completion_cost, 8)
