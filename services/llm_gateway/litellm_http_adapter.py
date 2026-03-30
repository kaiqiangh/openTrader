"""Backward-compatible shim — use openai_compatible_adapter directly."""

from services.llm_gateway.openai_compatible_adapter import (  # noqa: F401
    LLMProviderError as LiteLLMHTTPError,
    OpenAICompatibleClient as LiteLLMHTTPProviderClient,
)
