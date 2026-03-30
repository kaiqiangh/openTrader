from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query

from services.api.auth import require_operator, require_viewer
from services.api.dependencies import get_control_plane_repository, get_control_plane_state
from services.api.models import (
    AuthPrincipal,
    ExecutionMode,
    ModeAuditRecordResponse,
    ModeHistoryResponse,
    ModeResponse,
    ModeUpdateRequest,
    StrategyListResponse,
    StrategyRecordResponse,
    StrategyStateUpdateRequest,
)
from services.api.state import ControlPlaneState, ModeAuditRecord, StrategyRuntimeRecord

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/control", tags=["control"])


@router.get("/mode", response_model=ModeResponse)
def get_mode(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
) -> ModeResponse:
    return ModeResponse(mode=ExecutionMode(state.mode), updated_at=_last_mode_update_time(state))


@router.get("/mode/history", response_model=ModeHistoryResponse)
def get_mode_history(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
    limit: int = Query(default=50, ge=1, le=500),
) -> ModeHistoryResponse:
    records = state.list_mode_history(limit=limit)
    return ModeHistoryResponse(items=[_mode_audit_model(item) for item in records])


@router.put("/mode", response_model=ModeResponse)
def update_mode(
    body: ModeUpdateRequest,
    principal: AuthPrincipal = Depends(require_operator),
    state: ControlPlaneState = Depends(get_control_plane_state),
    repository: Any | None = Depends(get_control_plane_repository),
) -> ModeResponse:
    changed, changed_at = state.set_mode(mode=body.mode.value, actor=principal.user_id, reason=body.reason)
    if changed and repository is not None:
        try:
            repository.persist_mode_change(
                mode=state.mode,
                changed_by=principal.user_id,
                reason=body.reason,
                changed_at=changed_at,
                strategies=state.list_strategies(),
            )
        except Exception:
            _logger.warning("persist_mode_change_failed", exc_info=True)
    return ModeResponse(
        mode=ExecutionMode(state.mode),
        updated_at=changed_at,
        changed_by=principal.user_id,
        reason=body.reason,
    )


@router.get("/strategies", response_model=StrategyListResponse)
def list_strategies(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
) -> StrategyListResponse:
    return StrategyListResponse(items=[_strategy_model(item) for item in state.list_strategies()])


@router.put("/strategies/{strategy_id}/state", response_model=StrategyRecordResponse)
def update_strategy_state(
    strategy_id: str,
    body: StrategyStateUpdateRequest,
    principal: AuthPrincipal = Depends(require_operator),
    state: ControlPlaneState = Depends(get_control_plane_state),
    repository: Any | None = Depends(get_control_plane_repository),
) -> StrategyRecordResponse:
    updated = state.set_strategy_state(
        strategy_id=strategy_id,
        state=body.state.value,
        actor=principal.user_id,
        reason=body.reason,
    )
    if repository is not None:
        try:
            repository.upsert_strategy_state(updated)
        except Exception:
            _logger.warning("upsert_strategy_state_failed", exc_info=True)
    return _strategy_model(updated)


def _strategy_model(item: StrategyRuntimeRecord) -> StrategyRecordResponse:
    return StrategyRecordResponse(
        strategy_id=item.strategy_id,
        symbol=item.symbol,
        mode=ExecutionMode(item.mode),
        state=item.state,
        updated_at=item.updated_at,
        changed_by=item.changed_by,
        reason=item.reason,
    )


def _mode_audit_model(item: ModeAuditRecord) -> ModeAuditRecordResponse:
    return ModeAuditRecordResponse(
        event_id=item.event_id,
        mode=ExecutionMode(item.mode),
        changed_by=item.changed_by,
        reason=item.reason,
        changed_at=item.changed_at,
    )


def _last_mode_update_time(state: ControlPlaneState) -> str:
    items = state.list_mode_history(limit=1)
    if not items:
        return ""
    return items[0].changed_at
