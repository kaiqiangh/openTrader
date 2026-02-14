from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol
import asyncio
import time

from services.llm_gateway.contracts import (
    GatewaySettings,
    LLMRequest,
    LLMResponse,
    LLMRetryExhaustedError,
    ProviderNotConfiguredError,
    ProviderSettings,
)


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
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.provider_clients = dict(provider_clients)
        self._sleep = sleep
        self._monotonic_clock = monotonic_clock

    async def generate(
        self,
        request: LLMRequest,
        *,
        provider_order: Sequence[str] | None = None,
    ) -> LLMResponse:
        ordered_aliases = tuple(provider_order or self.settings.default_provider_order)
        if not ordered_aliases:
            raise LLMRetryExhaustedError("No provider aliases configured for gateway request")

        error_summaries: list[str] = []
        for alias in ordered_aliases:
            provider = self._get_provider(alias)
            if not provider.enabled:
                error_summaries.append(f"{alias}: provider_disabled")
                continue

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
                    return LLMResponse(
                        provider=alias,
                        model=provider.model,
                        content=self._extract_content(raw_payload),
                        raw_payload=raw_payload,
                        usage=self._extract_usage(raw_payload),
                        latency_ms=max(latency_ms, 0),
                        attempt_count=attempt_idx + 1,
                    )
                except Exception as exc:  # noqa: BLE001 - gateway intentionally normalizes provider errors
                    reason = exc.__class__.__name__
                    if isinstance(exc, asyncio.TimeoutError):
                        reason = "timeout"
                    error_summaries.append(f"{alias}:attempt{attempt_idx + 1}:{reason}")
                    if attempt_idx < provider.max_retries:
                        await self._sleep(self._retry_delay_seconds(attempt_idx))
                        continue
                    break

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

