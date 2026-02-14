from __future__ import annotations

from fastapi import APIRouter, Depends

from services.api.auth import require_operator, require_viewer
from services.api.dependencies import get_control_plane_state
from services.api.models import (
    AuthPrincipal,
    ExecutionMode,
    ModeResponse,
    ModeUpdateRequest,
    StrategyListResponse,
    StrategyRecordResponse,
    StrategyStateUpdateRequest,
)
from services.api.state import ControlPlaneState, StrategyRuntimeRecord

router = APIRouter(prefix="/control", tags=["control"])


@router.get("/mode", response_model=ModeResponse)
def get_mode(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
) -> ModeResponse:
    return ModeResponse(mode=ExecutionMode(state.mode), updated_at=_last_mode_update_time(state))


@router.put("/mode", response_model=ModeResponse)
def update_mode(
    body: ModeUpdateRequest,
    principal: AuthPrincipal = Depends(require_operator),
    state: ControlPlaneState = Depends(get_control_plane_state),
) -> ModeResponse:
    _, changed_at = state.set_mode(mode=body.mode.value, actor=principal.user_id, reason=body.reason)
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
) -> StrategyRecordResponse:
    updated = state.set_strategy_state(
        strategy_id=strategy_id,
        state=body.state.value,
        actor=principal.user_id,
        reason=body.reason,
    )
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


def _last_mode_update_time(state: ControlPlaneState) -> str:
    strategies = state.list_strategies()
    if not strategies:
        return ""
    return max(item.updated_at for item in strategies)
