"""Orchestrator worker runner with LLM and tracing helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from sqlalchemy.engine import Engine

from services.agent_orchestrator.contracts import StrategyConfig
from services.agent_orchestrator.llm_runtime import LLMDecisionRuntime
from services.agent_orchestrator.metrics_tracing import AgentRuntimeMetrics
from services.agent_orchestrator.sqlalchemy_trace_store import SQLAlchemyTraceStore, TraceAgentRun
from services.llm_gateway.contracts import GatewaySettings, ProviderSettings
from services.llm_gateway.gateway import LLMGateway
from services.llm_gateway.openai_compatible_adapter import OpenAICompatibleClient
from services.llm_gateway.sqlalchemy_stores import SQLAlchemyLLMCallStore, SQLAlchemyLLMQuotaStore
from services.workers.helpers import (
    _parse_csv_tokens,
    _to_bool,
    _utc_now_iso,
    _worker_activity_snapshot,
)
from services.workers.runtime_pipeline import AgentOrchestratorRuntimeWorker


def _strategy_from_settings(*, settings: Any) -> StrategyConfig:
    return StrategyConfig(
        strategy_id=settings.strategy_id,
        symbol=settings.symbol,
        mode=settings.mode,
        order_size=float(os.getenv("STRATEGY_ORDER_SIZE", "0.1")),
        planner_buy_threshold=float(os.getenv("STRATEGY_PLANNER_BUY_THRESHOLD", "0.2")),
        planner_sell_threshold=float(os.getenv("STRATEGY_PLANNER_SELL_THRESHOLD", "0.2")),
        risk_max_notional_usd=float(os.getenv("STRATEGY_RISK_MAX_NOTIONAL_USD", "50000")),
        risk_max_position_size=float(os.getenv("STRATEGY_RISK_MAX_POSITION_SIZE", "1.0")),
        risk_max_drawdown_pct=float(os.getenv("STRATEGY_RISK_MAX_DRAWDOWN_PCT", "0.3")),
        risk_min_confidence=float(os.getenv("STRATEGY_RISK_MIN_CONFIDENCE", "0.2")),
    )


def _build_llm_runtime(
    *,
    runtime_engine: Engine,
    metrics: AgentRuntimeMetrics,
) -> LLMDecisionRuntime | None:
    if not _to_bool(os.getenv("LLM_RUNTIME_ENABLED", "false")):
        return None

    base_url = os.getenv("LLM_BASE_URL", os.getenv("LITELLM_BASE_URL", "")).strip()
    if not base_url:
        return None

    timeout_seconds = max(0.1, float(os.getenv("LLM_TIMEOUT_SECONDS", os.getenv("LITELLM_TIMEOUT_SECONDS", "15.0"))))
    timeout_ms = max(1, int(timeout_seconds * 1000))
    retries = max(0, int(os.getenv("LLM_PROVIDER_MAX_RETRIES", "1")))

    quick_order = tuple(token.lower() for token in _parse_csv_tokens(os.getenv("LLM_QUICK_PROVIDER_ORDER", "default")))
    deep_order = tuple(token.lower() for token in _parse_csv_tokens(os.getenv("LLM_DEEP_PROVIDER_ORDER", "default")))
    default_order = quick_order or ("default",)
    normalized_model = _normalize_llm_model(
        base_url=base_url,
        model=os.getenv("LLM_MODEL", os.getenv("LITELLM_MODEL", "deepseek-chat")),
    )

    provider_aliases = _ordered_provider_aliases(default_order, deep_order)
    providers: dict[str, ProviderSettings] = {}
    for alias in provider_aliases:
        model = _resolve_provider_model(alias=alias, default_model=normalized_model)
        prompt_cost, completion_cost = _resolve_provider_costs(alias=alias)
        providers[alias] = ProviderSettings(
            alias=alias,
            model=model,
            timeout_ms=timeout_ms,
            max_retries=retries,
            enabled=True,
            prompt_cost_per_1k_tokens=prompt_cost,
            completion_cost_per_1k_tokens=completion_cost,
        )

    gateway_settings = GatewaySettings(
        providers=providers,
        default_provider_order=default_order,
        retry_base_ms=max(1, int(os.getenv("LLM_GATEWAY_RETRY_BASE_MS", "100"))),
        retry_max_ms=max(10, int(os.getenv("LLM_GATEWAY_RETRY_MAX_MS", "2000"))),
    )

    provider_client = OpenAICompatibleClient(
        base_url=base_url,
        api_key=os.getenv("LLM_API_KEY", os.getenv("LITELLM_API_KEY")),
        timeout_seconds=timeout_seconds,
    )
    gateway = LLMGateway(
        settings=gateway_settings,
        provider_clients={alias: provider_client for alias in provider_aliases},
        call_store=SQLAlchemyLLMCallStore(connection=runtime_engine),
        quota_store=SQLAlchemyLLMQuotaStore(connection=runtime_engine),
        metrics=metrics,
    )
    return LLMDecisionRuntime(
        gateway=gateway,
        quick_provider_order=default_order,
        deep_provider_order=deep_order or default_order,
        quick_temperature=float(os.getenv("LLM_QUICK_TEMPERATURE", "0.1")),
        deep_temperature=float(os.getenv("LLM_DEEP_TEMPERATURE", "0.2")),
    )


def _ordered_provider_aliases(*orders: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for order in orders:
        for raw_alias in order:
            alias = raw_alias.strip().lower()
            if not alias or alias in seen:
                continue
            seen.add(alias)
            ordered.append(alias)
    return tuple(ordered) or ("default",)


def _resolve_provider_model(*, alias: str, default_model: str) -> str:
    if alias == "default":
        return default_model
    if alias == "openai":
        return os.getenv("LLM_OPENAI_MODEL", "openai/gpt-4o-mini").strip() or "openai/gpt-4o-mini"
    if alias == "anthropic":
        return (
            os.getenv("LLM_ANTHROPIC_MODEL", "anthropic/claude-3-5-sonnet-20241022").strip()
            or "anthropic/claude-3-5-sonnet-20241022"
        )
    custom_model = os.getenv(f"LLM_{_provider_alias_env_token(alias)}_MODEL", "").strip()
    return custom_model or default_model


def _resolve_provider_costs(*, alias: str) -> tuple[float, float]:
    env_prefix = f"LLM_{_provider_alias_env_token(alias)}"
    if alias == "openai":
        prompt_cost_raw = os.getenv("LLM_OPENAI_PROMPT_COST_PER_1K")
        completion_cost_raw = os.getenv("LLM_OPENAI_COMPLETION_COST_PER_1K")
    elif alias == "anthropic":
        prompt_cost_raw = os.getenv("LLM_ANTHROPIC_PROMPT_COST_PER_1K")
        completion_cost_raw = os.getenv("LLM_ANTHROPIC_COMPLETION_COST_PER_1K")
    else:
        prompt_cost_raw = os.getenv(f"{env_prefix}_PROMPT_COST_PER_1K")
        completion_cost_raw = os.getenv(f"{env_prefix}_COMPLETION_COST_PER_1K")
    prompt_cost = float(prompt_cost_raw) if prompt_cost_raw else 0.0
    completion_cost = float(completion_cost_raw) if completion_cost_raw else 0.0
    return prompt_cost, completion_cost


def _provider_alias_env_token(alias: str) -> str:
    sanitized = "".join(ch if ch.isalnum() else "_" for ch in alias.strip().upper())
    return sanitized or "LITELLM"


def _normalize_llm_model(*, base_url: str, model: str) -> str:
    normalized_model = model.strip() or "deepseek-chat"
    # Strip provider prefix for direct API calls (e.g., "deepseek/deepseek-chat" → "deepseek-chat")
    if "/" in normalized_model:
        parts = normalized_model.split("/", 1)
        suffix = parts[1].strip()
        return suffix or normalized_model
    return normalized_model


def _orchestrator_activity_payload(
    *,
    result: Any,
    strategy: StrategyConfig,
    metrics_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    llm_providers = _extract_llm_provider_tags(
        tuple(getattr(result.plan, "rationale", ()) or ()),
        tuple(getattr(result.risk, "rationale", ()) or ()),
        tuple(getattr(result.execution_decision, "rationale", ()) or ()),
    )
    llm_totals: dict[str, Any] = {}
    llm_usage = metrics_snapshot.get("llm_usage")
    if isinstance(llm_usage, Mapping):
        totals = llm_usage.get("totals")
        if isinstance(totals, Mapping):
            llm_totals = {
                "calls_total": int(totals.get("calls_total", 0) or 0),
                "failed_calls_total": int(totals.get("failed_calls_total", 0) or 0),
                "tokens_total": int(totals.get("tokens_total", 0) or 0),
                "estimated_cost_total": float(totals.get("estimated_cost_total", 0.0) or 0.0),
            }
    return {
        "event": "agent.decision.completed",
        "trace_id": getattr(result, "trace_id", ""),
        "decision_id": getattr(result, "decision_id", ""),
        "strategy_id": strategy.strategy_id,
        "mode": getattr(result, "mode", ""),
        "status": getattr(result, "status", ""),
        "symbol": strategy.symbol,
        "action": getattr(result.execution_decision, "action", "HOLD"),
        "quantity": float(getattr(result.execution_decision, "quantity", 0.0) or 0.0),
        "confidence": float(getattr(result.execution_decision, "confidence", 0.0) or 0.0),
        "risk_approved": bool(getattr(result.risk, "approved", False)),
        "guardrail_allowed": bool(getattr(result.guardrail, "allowed", False)),
        "llm_provider_models": list(llm_providers),
        "llm_usage": llm_totals,
    }


def _extract_llm_provider_tags(*rationales: tuple[str, ...]) -> tuple[str, ...]:
    tags: list[str] = []
    prefix = "llm_provider="
    for rationale in rationales:
        for item in rationale:
            value = str(item).strip()
            if not value.startswith(prefix):
                continue
            provider_model = value[len(prefix):].strip()
            if provider_model:
                tags.append(provider_model)
    return tuple(dict.fromkeys(tags))


def _decision_spans(worker: AgentOrchestratorRuntimeWorker, *, decision_id: str) -> tuple[Mapping[str, Any], ...]:
    snapshot = worker.orchestrator.metrics.snapshot()
    spans = snapshot.get("recent_spans")
    if not isinstance(spans, list):
        return ()
    matched: list[Mapping[str, Any]] = []
    for span in spans:
        if not isinstance(span, Mapping):
            continue
        if str(span.get("decision_id", "")) != decision_id:
            continue
        matched.append(span)
    return tuple(matched)


def _build_trace_runs(
    *,
    result: Any,
    strategy: StrategyConfig,
    last_market_envelope: Mapping[str, Any] | None,
    recent_spans: tuple[Mapping[str, Any], ...],
) -> tuple[TraceAgentRun, ...]:
    span_by_stage = {str(item.get("stage", "")): item for item in recent_spans if isinstance(item, Mapping)}
    ordered_stages = (
        ("market_context_agent", "context", _context_stage_input(last_market_envelope), _context_stage_output(result)),
        ("planner_agent", "planner", _planner_stage_input(result), _planner_stage_output(result)),
        ("risk_agent", "risk", _risk_stage_input(result, strategy), _risk_stage_output(result)),
        (
            "execution_decision_agent",
            "execution",
            _execution_stage_input(result),
            _execution_stage_output(result),
        ),
        ("guardrail_validation", "guardrail", _guardrail_stage_input(result), _guardrail_stage_output(result)),
    )
    runs: list[TraceAgentRun] = []
    for stage_key, agent_name, input_payload, output_payload in ordered_stages:
        span = span_by_stage.get(stage_key)
        if span is None:
            status = "succeeded"
            latency_ms = None
            started_at = _decision_started_at(result.lifecycle)
            completed_at = _decision_completed_at(result.lifecycle)
        else:
            status = str(span.get("status", "succeeded"))
            latency_raw = span.get("latency_ms")
            latency_ms = float(latency_raw) if latency_raw is not None else None
            started_at = str(span.get("started_at", _utc_now_iso()))
            completed_at_raw = span.get("completed_at")
            completed_at = str(completed_at_raw) if completed_at_raw else None
        runs.append(
            TraceAgentRun(
                agent_name=agent_name,
                status=status,
                latency_ms=latency_ms,
                started_at=started_at,
                completed_at=completed_at,
                input_payload=input_payload,
                output_payload=output_payload,
            )
        )
    return tuple(runs)


def _context_stage_input(last_market_envelope: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(last_market_envelope, Mapping):
        return {}
    payload = last_market_envelope.get("payload")
    if not isinstance(payload, Mapping):
        return {}
    return {
        "exchange": payload.get("exchange"),
        "symbol": payload.get("symbol"),
        "timestamp_ms": payload.get("timestamp_ms"),
        "bids": _safe_list(payload.get("bids")),
        "asks": _safe_list(payload.get("asks")),
        "news": _safe_mapping(payload.get("news")),
    }


def _context_stage_output(result: Any) -> dict[str, Any]:
    output = {
        "context": _to_payload_mapping(getattr(result.market_context, "context", {})),
        "microstructure": _to_payload_mapping(getattr(result.market_context, "microstructure", {})),
        "news": _to_payload_mapping(getattr(result.market_context, "news", {})),
        "quality": _to_payload_mapping(getattr(result.market_context, "quality", {})),
        "notes": list(getattr(result.market_context, "notes", ()) or ()),
    }
    return output


def _planner_stage_input(result: Any) -> dict[str, Any]:
    return {"market_context": _to_payload_mapping(getattr(result.market_context, "context", {}))}


def _planner_stage_output(result: Any) -> dict[str, Any]:
    return _to_payload_mapping(getattr(result, "plan", {}))


def _risk_stage_input(result: Any, strategy: StrategyConfig) -> dict[str, Any]:
    return {
        "plan": _to_payload_mapping(getattr(result, "plan", {})),
        "market_context": _to_payload_mapping(getattr(result.market_context, "context", {})),
        "strategy": _to_payload_mapping(strategy),
    }


def _risk_stage_output(result: Any) -> dict[str, Any]:
    return _to_payload_mapping(getattr(result, "risk", {}))


def _execution_stage_input(result: Any) -> dict[str, Any]:
    return {
        "plan": _to_payload_mapping(getattr(result, "plan", {})),
        "risk": _to_payload_mapping(getattr(result, "risk", {})),
        "market_context": _to_payload_mapping(getattr(result.market_context, "context", {})),
    }


def _execution_stage_output(result: Any) -> dict[str, Any]:
    return _to_payload_mapping(getattr(result, "execution_decision", {}))


def _guardrail_stage_input(result: Any) -> dict[str, Any]:
    return {
        "plan": _to_payload_mapping(getattr(result, "plan", {})),
        "risk": _to_payload_mapping(getattr(result, "risk", {})),
        "execution_decision": _to_payload_mapping(getattr(result, "execution_decision", {})),
        "market_context": _to_payload_mapping(getattr(result.market_context, "context", {})),
    }


def _guardrail_stage_output(result: Any) -> dict[str, Any]:
    return _to_payload_mapping(getattr(result, "guardrail", {}))


def _decision_started_at(lifecycle: tuple[Mapping[str, Any], ...]) -> str:
    if lifecycle:
        first = lifecycle[0]
        emitted_at = first.get("emitted_at")
        if isinstance(emitted_at, str) and emitted_at.strip():
            return emitted_at
    return _utc_now_iso()


def _decision_completed_at(lifecycle: tuple[Mapping[str, Any], ...]) -> str:
    if lifecycle:
        last = lifecycle[-1]
        emitted_at = last.get("emitted_at")
        if isinstance(emitted_at, str) and emitted_at.strip():
            return emitted_at
    return _utc_now_iso()


def _decision_news_links(last_market_envelope: Mapping[str, Any] | None) -> tuple[tuple[str, str], ...]:
    from services.workers.helpers import _maybe_uuid

    if not isinstance(last_market_envelope, Mapping):
        return ()
    payload = last_market_envelope.get("payload")
    if not isinstance(payload, Mapping):
        return ()
    news = payload.get("news")
    if not isinstance(news, Mapping):
        return ()
    summary_id = _maybe_uuid(news.get("summary_id"))
    if summary_id is None:
        return ()
    news_ids: list[str] = []
    candidate_ids = news.get("news_ids")
    if isinstance(candidate_ids, list):
        for raw in candidate_ids:
            parsed = _maybe_uuid(raw)
            if parsed is not None:
                news_ids.append(parsed)
    items = news.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, Mapping):
                continue
            parsed = _maybe_uuid(item.get("news_id"))
            if parsed is not None:
                news_ids.append(parsed)
    deduped_news_ids = tuple(dict.fromkeys(news_ids))
    return tuple((summary_id, news_id) for news_id in deduped_news_ids)


def _to_payload_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    return {}


def _safe_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return dict(value)


def _safe_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return list(value)


# ── OrchestratorWorkerRunner ──────────────────────────────────────────────────

class OrchestratorWorkerRunner:
    def __init__(
        self,
        *,
        worker: AgentOrchestratorRuntimeWorker,
        strategy: StrategyConfig,
        trace_store: SQLAlchemyTraceStore | None = None,
    ) -> None:
        self.worker = worker
        self.strategy = strategy
        self.trace_store = trace_store
        self._last_activity: dict[str, Any] = {}

    async def run_once(self, *, timeout_seconds: float) -> bool:
        result = await self.worker.run_once(
            strategy=self.strategy,
            timeout_seconds=timeout_seconds,
        )
        if result is None:
            self._last_activity = {"event": "no_market_event", "strategy_id": self.strategy.strategy_id}
            return False
        if self.trace_store is not None:
            await self.trace_store.persist_cycle(
                trace_id=result.trace_id,
                decision_id=result.decision_id,
                strategy_id=self.strategy.strategy_id,
                mode=result.mode,
                status=result.status,
                started_at=_decision_started_at(result.lifecycle),
                completed_at=_decision_completed_at(result.lifecycle),
                runs=_build_trace_runs(
                    result=result,
                    strategy=self.strategy,
                    last_market_envelope=self.worker.last_envelope,
                    recent_spans=_decision_spans(self.worker, decision_id=result.decision_id),
                ),
                decision_news_links=_decision_news_links(self.worker.last_envelope),
            )
        self._last_activity = _orchestrator_activity_payload(
            result=result,
            strategy=self.strategy,
            metrics_snapshot=self.worker.orchestrator.metrics.snapshot(),
        )
        return True

    def activity_snapshot(self) -> dict[str, Any]:
        return dict(self._last_activity)
