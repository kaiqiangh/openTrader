from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from services.api.auth import require_viewer
from services.api.dependencies import get_control_plane_state
from services.api.models import (
    AuthPrincipal,
    LLMCallLogListResponse,
    LLMCallLogRecordResponse,
    LLMBreachListResponse,
    LLMBreachRecordResponse,
    LLMUsageListResponse,
    LLMUsageRecordResponse,
    UserRole,
)
from services.api.state import ControlPlaneState, LLMCallLogRecord, LLMBreachRecord, LLMUsageRecord

router = APIRouter(prefix="/governance", tags=["governance"])


@router.get("/llm/usage", response_model=LLMUsageListResponse)
def list_llm_usage(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
    strategy_id: str | None = Query(default=None),
    agent_name: str | None = Query(default=None),
) -> LLMUsageListResponse:
    items = state.list_llm_usage(strategy_id=strategy_id, agent_name=agent_name)
    return LLMUsageListResponse(items=[_usage_model(item) for item in items])


@router.get("/llm/breaches", response_model=LLMBreachListResponse)
def list_llm_breaches(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
    strategy_id: str | None = Query(default=None),
    agent_name: str | None = Query(default=None),
    include_failures: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=500),
) -> LLMBreachListResponse:
    items = state.list_llm_breaches(
        strategy_id=strategy_id,
        agent_name=agent_name,
        include_failures=include_failures,
        limit=limit,
    )
    return LLMBreachListResponse(items=[_breach_model(item) for item in items])


@router.get("/llm/calls", response_model=LLMCallLogListResponse)
def list_llm_calls(
    principal: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
    strategy_id: str | None = Query(default=None),
    agent_name: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> LLMCallLogListResponse:
    items = state.list_llm_call_logs(
        strategy_id=strategy_id,
        agent_name=agent_name,
        status=status_filter,
        limit=limit,
    )
    is_admin = principal.role == UserRole.ADMIN
    return LLMCallLogListResponse(items=[_call_model(item, include_previews=is_admin) for item in items])


def _usage_model(item: LLMUsageRecord) -> LLMUsageRecordResponse:
    return LLMUsageRecordResponse(
        strategy_id=item.strategy_id,
        agent_name=item.agent_name,
        daily_tokens=item.daily_tokens,
        monthly_cost=item.monthly_cost,
        total_calls=item.total_calls,
        breach_count=item.breach_count,
        daily_token_limit=item.daily_token_limit,
        monthly_cost_limit=item.monthly_cost_limit,
        is_hard_limit=item.is_hard_limit,
        daily_utilization_ratio=item.daily_utilization_ratio,
        monthly_utilization_ratio=item.monthly_utilization_ratio,
        window_date=item.window_date,
        window_month=item.window_month,
    )


def _breach_model(item: LLMBreachRecord) -> LLMBreachRecordResponse:
    return LLMBreachRecordResponse(
        llm_call_id=item.llm_call_id,
        strategy_id=item.strategy_id,
        agent_name=item.agent_name,
        trace_id=item.trace_id,
        decision_id=item.decision_id,
        reason=item.reason,
        projected_tokens=item.projected_tokens,
        projected_cost=item.projected_cost,
        created_at=item.created_at,
    )


def _call_model(item: LLMCallLogRecord, *, include_previews: bool = False) -> LLMCallLogRecordResponse:
    return LLMCallLogRecordResponse(
        llm_call_id=item.llm_call_id,
        trace_id=item.trace_id,
        decision_id=item.decision_id,
        strategy_id=item.strategy_id,
        agent_name=item.agent_name,
        provider=item.provider,
        model=item.model,
        status=item.status,
        mode=item.mode,
        tier=item.tier,
        prompt_tokens=item.prompt_tokens,
        completion_tokens=item.completion_tokens,
        total_tokens=item.total_tokens,
        latency_ms=item.latency_ms,
        estimated_cost=item.estimated_cost,
        created_at=item.created_at,
        prompt_preview=item.prompt_preview if include_previews else None,
        response_preview=item.response_preview if include_previews else None,
    )
