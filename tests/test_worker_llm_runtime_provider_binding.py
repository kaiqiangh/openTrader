from __future__ import annotations

from sqlalchemy import create_engine

from services.agent_orchestrator.metrics_tracing import AgentRuntimeMetrics
from services.workers.main import _build_llm_runtime


def test_build_llm_runtime_defaults_to_litellm_alias_with_deepseek_normalization(monkeypatch) -> None:
    monkeypatch.setenv("LLM_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("LITELLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("LITELLM_MODEL", "deepseek/deepseek-chat")
    monkeypatch.delenv("LLM_QUICK_PROVIDER_ORDER", raising=False)
    monkeypatch.delenv("LLM_DEEP_PROVIDER_ORDER", raising=False)

    runtime = _build_llm_runtime(
        runtime_engine=create_engine("sqlite+pysqlite:///:memory:", future=True),
        metrics=AgentRuntimeMetrics(),
    )

    assert runtime is not None
    assert runtime.quick_provider_order == ("litellm",)
    assert runtime.deep_provider_order == ("litellm",)
    provider = runtime.gateway.settings.providers["litellm"]
    assert provider.model == "deepseek-chat"


def test_build_llm_runtime_supports_explicit_openai_anthropic_alias_orders(monkeypatch) -> None:
    monkeypatch.setenv("LLM_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm:4000")
    monkeypatch.setenv("LITELLM_MODEL", "deepseek/deepseek-chat")
    monkeypatch.setenv("LLM_QUICK_PROVIDER_ORDER", "openai,anthropic")
    monkeypatch.setenv("LLM_DEEP_PROVIDER_ORDER", "anthropic,openai")
    monkeypatch.setenv("LLM_OPENAI_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setenv("LLM_ANTHROPIC_MODEL", "anthropic/claude-3-5-sonnet-20241022")

    runtime = _build_llm_runtime(
        runtime_engine=create_engine("sqlite+pysqlite:///:memory:", future=True),
        metrics=AgentRuntimeMetrics(),
    )

    assert runtime is not None
    assert runtime.quick_provider_order == ("openai", "anthropic")
    assert runtime.deep_provider_order == ("anthropic", "openai")
    assert set(runtime.gateway.settings.providers) == {"openai", "anthropic"}
