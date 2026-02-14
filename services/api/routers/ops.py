from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.api.auth import require_admin, require_operator, require_viewer
from services.api.dependencies import get_control_plane_state
from services.api.models import (
    AuthPrincipal,
    ExecutionMode,
    OrderListResponse,
    OrderRecordResponse,
    PortfolioSnapshotResponse,
    PositionListResponse,
    PositionRecordResponse,
    RiskControlActionResponse,
    RiskControlCommandRequest,
    RiskControlEventResponse,
    RiskStatusResponse,
)
from services.api.state import ControlPlaneState
from services.oms import PortfolioSnapshot, PositionState, ReconciliationOrder, RiskControlEvent

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get("/orders", response_model=OrderListResponse)
def list_orders(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
    status_filter: str | None = Query(default=None, alias="status"),
    mode: str | None = Query(default=None),
) -> OrderListResponse:
    items = state.list_orders(status=status_filter, mode=mode)
    return OrderListResponse(items=[_order_model(item) for item in items])


@router.get("/positions", response_model=PositionListResponse)
def list_positions(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
    mode: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
) -> PositionListResponse:
    items = state.list_positions(mode=mode, symbol=symbol)
    return PositionListResponse(items=[_position_model(item) for item in items])


@router.get("/portfolio/latest", response_model=PortfolioSnapshotResponse)
def get_latest_portfolio_snapshot(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
    mode: str | None = Query(default=None),
) -> PortfolioSnapshotResponse:
    snapshot = state.latest_snapshot(mode=mode)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No portfolio snapshot found")
    return _snapshot_model(snapshot)


@router.get("/risk/status", response_model=RiskStatusResponse)
def get_risk_status(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
) -> RiskStatusResponse:
    status_payload, recent_events = state.risk_status()
    return RiskStatusResponse(
        kill_switch_enabled=bool(status_payload["kill_switch_enabled"]),
        circuit_breaker_open=bool(status_payload["circuit_breaker_open"]),
        consecutive_failures=int(status_payload["consecutive_failures"]),
        circuit_breaker_open_until=status_payload["circuit_breaker_open_until"],
        blocked_by=[str(item) for item in status_payload["blocked_by"]],
        recent_events=[_risk_event_model(item) for item in recent_events[-10:]],
    )


@router.post("/risk/circuit-breaker/trip", response_model=RiskControlActionResponse)
def trip_circuit_breaker(
    body: RiskControlCommandRequest,
    principal: AuthPrincipal = Depends(require_operator),
    state: ControlPlaneState = Depends(get_control_plane_state),
) -> RiskControlActionResponse:
    event = state.trip_circuit_breaker(
        reason=body.reason,
        actor=principal.user_id,
        cooldown_seconds=body.cooldown_seconds,
    )
    return _risk_action_model(event)


@router.post("/risk/circuit-breaker/reset", response_model=RiskControlActionResponse)
def reset_circuit_breaker(
    body: RiskControlCommandRequest,
    principal: AuthPrincipal = Depends(require_operator),
    state: ControlPlaneState = Depends(get_control_plane_state),
) -> RiskControlActionResponse:
    event = state.reset_circuit_breaker(reason=body.reason, actor=principal.user_id)
    return _risk_action_model(event)


@router.post("/risk/kill-switch/enable", response_model=RiskControlActionResponse)
def enable_kill_switch(
    body: RiskControlCommandRequest,
    principal: AuthPrincipal = Depends(require_admin),
    state: ControlPlaneState = Depends(get_control_plane_state),
) -> RiskControlActionResponse:
    event = state.enable_kill_switch(reason=body.reason, actor=principal.user_id)
    return _risk_action_model(event)


@router.post("/risk/kill-switch/disable", response_model=RiskControlActionResponse)
def disable_kill_switch(
    body: RiskControlCommandRequest,
    principal: AuthPrincipal = Depends(require_admin),
    state: ControlPlaneState = Depends(get_control_plane_state),
) -> RiskControlActionResponse:
    event = state.disable_kill_switch(reason=body.reason, actor=principal.user_id)
    return _risk_action_model(event)


def _order_model(item: ReconciliationOrder) -> OrderRecordResponse:
    return OrderRecordResponse(
        order_id=item.order_id,
        symbol=item.symbol,
        mode=ExecutionMode(item.mode.strip().upper()),
        status=item.status,
        requested_quantity=item.requested_quantity,
        filled_quantity=item.filled_quantity,
        average_price=item.average_price,
    )


def _position_model(item: PositionState) -> PositionRecordResponse:
    return PositionRecordResponse(
        mode=ExecutionMode(item.mode.strip().upper()),
        symbol=item.symbol,
        quantity=item.quantity,
        average_entry_price=item.average_entry_price,
        realized_pnl=item.realized_pnl,
        status=item.status,
        updated_at=item.updated_at,
    )


def _snapshot_model(item: PortfolioSnapshot) -> PortfolioSnapshotResponse:
    return PortfolioSnapshotResponse(
        snapshot_time=item.snapshot_time,
        mode=ExecutionMode(item.mode.strip().upper()),
        total_balance_usd=item.total_balance_usd,
        available_balance_usd=item.available_balance_usd,
        locked_balance_usd=item.locked_balance_usd,
        unrealized_pnl=item.unrealized_pnl,
        realized_pnl_today=item.realized_pnl_today,
    )


def _risk_event_model(item: RiskControlEvent) -> RiskControlEventResponse:
    return RiskControlEventResponse(
        event_type=item.event_type,
        control=item.control,
        status=item.status,
        reason=item.reason,
        actor=item.actor,
        occurred_at=item.occurred_at,
        metadata=item.metadata,
    )


def _risk_action_model(item: RiskControlEvent) -> RiskControlActionResponse:
    return RiskControlActionResponse(
        event_type=item.event_type,
        control=item.control,
        status=item.status,
        reason=item.reason,
        changed_by=item.actor,
        occurred_at=item.occurred_at,
        metadata=item.metadata,
    )
