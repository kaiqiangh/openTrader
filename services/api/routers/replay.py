from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.agent_orchestrator.replay_service import DecisionReplayNotFoundError, DecisionReplayResult
from services.api.auth import require_viewer
from services.api.dependencies import get_control_plane_repository, get_control_plane_state
from services.api.models import (
    AuthPrincipal,
    ReplayCatalogDecisionRecordResponse,
    ReplayCatalogRequestRecordResponse,
    ReplayCatalogResponse,
    ReplayDecisionResultResponse,
    ReplayRequestCreateRequest,
    ReplayRequestResponse,
)
from services.api.state import ControlPlaneState, ReplayRequestRecord

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/replay", tags=["replay"])


@router.post("/requests", response_model=ReplayRequestResponse)
async def submit_replay_request(
    body: ReplayRequestCreateRequest,
    principal: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
    repository: Any | None = Depends(get_control_plane_repository),
) -> ReplayRequestResponse:
    try:
        request_record = await state.submit_replay_request(
            decision_id=body.decision_id,
            requested_by=principal.user_id,
        )
    except DecisionReplayNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if repository is not None:
        try:
            repository.persist_replay_request(request_record)
        except Exception:
            _logger.warning("persist_replay_request_failed", exc_info=True)
    return _request_model(request_record)


@router.get("/requests/{request_id}", response_model=ReplayRequestResponse)
def get_replay_request(
    request_id: str,
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
) -> ReplayRequestResponse:
    request_record = state.get_replay_request(request_id=request_id)
    if request_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Replay request not found")
    return _request_model(request_record)


@router.get("/decisions/{decision_id}", response_model=ReplayDecisionResultResponse)
async def get_replay_decision(
    decision_id: str,
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
) -> ReplayDecisionResultResponse:
    try:
        result = await state.replay_decision(decision_id=decision_id)
    except DecisionReplayNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _result_model(result)


@router.get("/catalog", response_model=ReplayCatalogResponse)
def get_replay_catalog(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
    decision_limit: int = Query(default=200, ge=1, le=1000),
    request_limit: int = Query(default=200, ge=1, le=1000),
) -> ReplayCatalogResponse:
    traces = state.list_replay_traces()[:decision_limit]
    requests = state.list_replay_requests(limit=request_limit)
    return ReplayCatalogResponse(
        decisions=[
            ReplayCatalogDecisionRecordResponse(
                decision_id=item.decision_id,
                trace_id=item.trace_id,
                strategy_id=item.strategy_id,
                mode=item.mode,
                status=item.status,
                started_at=item.started_at,
                completed_at=item.completed_at or "",
            )
            for item in traces
        ],
        requests=[
            ReplayCatalogRequestRecordResponse(
                request_id=item.request_id,
                decision_id=item.decision_id,
                status=item.status,
                requested_by=item.requested_by,
                requested_at=item.requested_at,
            )
            for item in requests
        ],
    )


def _request_model(record: ReplayRequestRecord) -> ReplayRequestResponse:
    return ReplayRequestResponse(
        request_id=record.request_id,
        decision_id=record.decision_id,
        status=record.status,
        requested_by=record.requested_by,
        requested_at=record.requested_at,
        result=_result_model(record.result),
    )


def _result_model(result: DecisionReplayResult) -> ReplayDecisionResultResponse:
    return ReplayDecisionResultResponse(
        decision_id=result.decision_id,
        trace_id=result.trace_id,
        strategy_id=result.strategy_id,
        mode=result.mode,
        status=result.status,
        summary=dict(result.summary),
        lifecycle=[dict(item) for item in result.lifecycle],
        agent_runs=[dict(item) for item in result.agent_runs],
        llm_calls=[dict(item) for item in result.llm_calls],
        graph_nodes=[asdict(item) for item in result.graph_nodes],
        graph_edges=[asdict(item) for item in result.graph_edges],
        deterministic_digest=result.deterministic_digest,
    )
