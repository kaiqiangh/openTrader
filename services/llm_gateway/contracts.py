from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ProviderSettings:
    alias: str
    model: str
    timeout_ms: int
    max_retries: int
    enabled: bool = True
    prompt_cost_per_1k_tokens: float = 0.0
    completion_cost_per_1k_tokens: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GatewaySettings:
    providers: dict[str, ProviderSettings]
    default_provider_order: tuple[str, ...]
    retry_base_ms: int = 100
    retry_max_ms: int = 2_000


@dataclass(frozen=True, slots=True)
class LLMRequest:
    trace_id: str
    decision_id: str
    strategy_id: str
    agent_name: str
    messages: tuple[Mapping[str, Any], ...]
    temperature: float
    max_tokens: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LLMResponse:
    provider: str
    model: str
    content: str
    raw_payload: Mapping[str, Any]
    usage: dict[str, int]
    latency_ms: int
    attempt_count: int


class LLMGatewayError(RuntimeError):
    """Base gateway failure."""


class ProviderNotConfiguredError(LLMGatewayError):
    """Raised when configured provider alias has no client implementation."""


class LLMRetryExhaustedError(LLMGatewayError):
    """Raised when all retries and fallback providers are exhausted."""


class LLMQuotaExceededError(LLMGatewayError):
    """Raised when hard-limit quota policy blocks a request before dispatch."""
