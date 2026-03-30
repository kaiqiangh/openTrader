from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from services.api.auth import require_admin, require_operator, require_viewer
from services.api.dependencies import get_api_settings, get_control_plane_repository, get_control_plane_state
from services.api.models import (
    AuthPrincipal,
    ExecutionMode,
    LLMRuntimeStatusResponse,
    MarketKlineListResponse,
    MarketKlineRecordResponse,
    NotificationDeliveryListResponse,
    NotificationDeliveryRecordResponse,
    NotificationMetricsResponse,
    NotificationMetricsTotalsResponse,
    NotificationPreferenceListResponse,
    NotificationPreferenceResponse,
    NotificationTraceListResponse,
    NotificationTraceRecordResponse,
    NotificationPreferenceUpsertRequest,
    NewsImpactListResponse,
    NewsImpactRecordResponse,
    NewsItemListResponse,
    NewsItemResponse,
    NewsSummaryListResponse,
    NewsSummaryResponse,
    OrderBookLevelResponse,
    OrderBookSnapshotResponse,
    OrderListResponse,
    OrderRecordResponse,
    PipelineHealthResponse,
    PipelineStageStatusResponse,
    PortfolioHistoryResponse,
    PortfolioSnapshotResponse,
    PositionListResponse,
    PositionRecordResponse,
    RiskControlActionResponse,
    RiskControlCommandRequest,
    RiskControlEventResponse,
    RiskStatusResponse,
    SignalListResponse,
    SignalRecordResponse,
    TradeListResponse,
    TradeRecordResponse,
)
from services.api.settings import APISettings
from services.api.state import (
    ControlPlaneState,
    NewsImpactRecord,
    NewsPanelItem,
    NewsPanelSummary,
    NotificationDeliveryRecord,
    NotificationPreferenceRecord,
    NotificationTraceRecord,
)
from services.oms import PortfolioSnapshot, PositionState, ReconciliationOrder, RiskControlEvent

_logger = logging.getLogger(__name__)

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


@router.get("/market/klines", response_model=MarketKlineListResponse)
def get_market_klines(
    _: AuthPrincipal = Depends(require_viewer),
    repository: Any | None = Depends(get_control_plane_repository),
    symbol: str = Query(min_length=1),
    interval: str = Query(default="1m", min_length=1),
    exchange: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=10000),
) -> MarketKlineListResponse:
    if repository is None:
        return MarketKlineListResponse(items=[])
    try:
        rows = repository.list_market_klines(
            symbol=symbol,
            interval=interval,
            exchange=exchange,
            limit=limit,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="market data repository unavailable",
        ) from exc
    return MarketKlineListResponse(items=[_kline_model(item) for item in rows])


@router.get("/market/orderbook/latest", response_model=OrderBookSnapshotResponse)
def get_latest_orderbook_snapshot(
    _: AuthPrincipal = Depends(require_viewer),
    repository: Any | None = Depends(get_control_plane_repository),
    symbol: str = Query(min_length=1),
    exchange: str | None = Query(default=None),
) -> OrderBookSnapshotResponse:
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No orderbook snapshot found")
    try:
        payload = repository.latest_orderbook_snapshot(symbol=symbol, exchange=exchange)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="market data repository unavailable",
        ) from exc
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No orderbook snapshot found")
    return _orderbook_snapshot_model(payload)


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


@router.get("/portfolio/history", response_model=PortfolioHistoryResponse)
def get_portfolio_history(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
    repository: Any | None = Depends(get_control_plane_repository),
    mode: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> PortfolioHistoryResponse:
    if repository is not None:
        try:
            items = repository.list_portfolio_history(mode=mode, limit=limit)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="portfolio repository unavailable",
            ) from exc
        return PortfolioHistoryResponse(items=[_snapshot_model(item) for item in items])

    mode_filter = mode.strip().upper() if mode else None
    snapshots = state.portfolio_snapshots
    if mode_filter is not None:
        snapshots = [item for item in snapshots if item.mode.strip().upper() == mode_filter]
    snapshots = sorted(snapshots, key=lambda item: item.snapshot_time)
    return PortfolioHistoryResponse(items=[_snapshot_model(item) for item in snapshots[:limit]])


@router.get("/signals/latest", response_model=SignalListResponse)
def get_latest_signals(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
    repository: Any | None = Depends(get_control_plane_repository),
    limit: int = Query(default=50, ge=1, le=500),
) -> SignalListResponse:
    if repository is not None:
        try:
            payload = repository.list_latest_signals(limit=limit)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="signal repository unavailable",
            ) from exc
        return SignalListResponse(items=[_signal_model(item) for item in payload])

    summaries = sorted(state.replay_summaries.values(), key=lambda item: item.persisted_at, reverse=True)[:limit]
    items: list[SignalRecordResponse] = []
    for summary in summaries:
        execution_decision = summary.summary.get("execution_decision", {})
        action = "HOLD"
        quantity = 0.0
        confidence = 0.0
        if isinstance(execution_decision, dict):
            action = str(execution_decision.get("action", "HOLD"))
            quantity = float(execution_decision.get("quantity", 0.0) or 0.0)
            confidence = float(execution_decision.get("confidence", 0.0) or 0.0)
        items.append(
            SignalRecordResponse(
                decision_id=summary.decision_id,
                trace_id=summary.trace_id,
                strategy_id=summary.strategy_id,
                mode=summary.mode,
                status=summary.status,
                action=action,
                quantity=quantity,
                confidence=confidence,
                created_at=summary.persisted_at,
            )
        )
    return SignalListResponse(items=items)


@router.get("/trades/latest", response_model=TradeListResponse)
def get_latest_trades(
    _: AuthPrincipal = Depends(require_viewer),
    repository: Any | None = Depends(get_control_plane_repository),
    mode: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> TradeListResponse:
    if repository is None:
        return TradeListResponse(items=[])
    try:
        payload = repository.list_latest_trades(mode=mode, symbol=symbol, limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="trade repository unavailable",
        ) from exc
    return TradeListResponse(items=[_trade_model(item) for item in payload])


@router.get("/pipeline/health", response_model=PipelineHealthResponse)
def get_pipeline_health(
    _: AuthPrincipal = Depends(require_viewer),
    repository: Any | None = Depends(get_control_plane_repository),
    mode: str | None = Query(default=None),
) -> PipelineHealthResponse:
    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="pipeline repository unavailable",
        )
    try:
        payload = repository.pipeline_health_snapshot(mode=mode)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="pipeline health query failed",
        ) from exc

    stages_raw = payload.get("stages")
    stages: list[PipelineStageStatusResponse] = []
    if isinstance(stages_raw, (list, tuple)):
        for row in stages_raw:
            if not isinstance(row, dict):
                continue
            stages.append(
                PipelineStageStatusResponse(
                    stage=str(row.get("stage", "")),
                    healthy=bool(row.get("healthy", False)),
                    status=str(row.get("status", "")),
                    records_total=int(row.get("records_total", 0) or 0),
                    latest_at=(str(row.get("latest_at")) if row.get("latest_at") is not None else None),
                    age_seconds=(float(row["age_seconds"]) if row.get("age_seconds") is not None else None),
                    stale_after_seconds=float(row.get("stale_after_seconds", 0.0) or 0.0),
                    detail=(str(row.get("detail")) if row.get("detail") is not None else None),
                )
            )

    return PipelineHealthResponse(
        generated_at=str(payload.get("generated_at", "")),
        overall_healthy=bool(payload.get("overall_healthy", False)),
        mode_filter=(str(payload.get("mode_filter")) if payload.get("mode_filter") is not None else None),
        stages=stages,
    )


@router.get("/llm/runtime", response_model=LLMRuntimeStatusResponse)
def get_llm_runtime_status(
    _: AuthPrincipal = Depends(require_viewer),
    settings: APISettings = Depends(get_api_settings),
    repository: Any | None = Depends(get_control_plane_repository),
) -> LLMRuntimeStatusResponse:
    snapshot = {
        "total_calls": 0,
        "succeeded_calls": 0,
        "failed_calls": 0,
        "latest_call_at": None,
    }
    if repository is not None:
        try:
            snapshot = repository.llm_runtime_status_snapshot()
        except Exception:
            _logger.warning("llm_runtime_status_snapshot_failed", exc_info=True)
    return LLMRuntimeStatusResponse(
        runtime_enabled=settings.llm_runtime_enabled,
        litellm_base_url_configured=bool(settings.litellm_base_url),
        quick_provider_order=list(settings.llm_quick_provider_order),
        deep_provider_order=list(settings.llm_deep_provider_order),
        total_calls=int(snapshot.get("total_calls", 0) or 0),
        succeeded_calls=int(snapshot.get("succeeded_calls", 0) or 0),
        failed_calls=int(snapshot.get("failed_calls", 0) or 0),
        latest_call_at=(
            str(snapshot.get("latest_call_at"))
            if snapshot.get("latest_call_at") is not None
            else None
        ),
    )


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


@router.get("/news/items", response_model=NewsItemListResponse)
def list_news_items(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
    symbol: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> NewsItemListResponse:
    items = state.list_news_items(symbol=symbol, limit=limit)
    return NewsItemListResponse(items=[_news_item_model(item) for item in items])


@router.get("/news/summaries", response_model=NewsSummaryListResponse)
def list_news_summaries(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
    symbol_scope: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
) -> NewsSummaryListResponse:
    items = state.list_news_summaries(symbol_scope=symbol_scope, limit=limit)
    return NewsSummaryListResponse(items=[_news_summary_model(item) for item in items])


@router.get("/news/impact", response_model=NewsImpactListResponse)
def list_news_impact(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
    limit: int = Query(default=10, ge=1, le=100),
) -> NewsImpactListResponse:
    items = state.list_news_impact(limit=limit)
    return NewsImpactListResponse(items=[_news_impact_model(item) for item in items])


@router.get("/notifications/preferences", response_model=NotificationPreferenceListResponse)
def list_notification_preferences(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
    user_id: str | None = Query(default=None),
) -> NotificationPreferenceListResponse:
    try:
        items = state.list_notification_preferences(user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return NotificationPreferenceListResponse(items=[_notification_preference_model(item) for item in items])


@router.put("/notifications/preferences/{user_id}", response_model=NotificationPreferenceResponse)
def upsert_notification_preference(
    user_id: str,
    body: NotificationPreferenceUpsertRequest,
    principal: AuthPrincipal = Depends(require_admin),
    state: ControlPlaneState = Depends(get_control_plane_state),
    repository: Any | None = Depends(get_control_plane_repository),
) -> NotificationPreferenceResponse:
    try:
        updated = state.upsert_notification_preference(
            user_id=user_id,
            min_severity=body.min_severity.value,
            gateways=body.gateways,
            strategy_ids=body.strategy_ids,
            event_types=body.event_types,
            actor=principal.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if repository is not None:
        try:
            repository.upsert_notification_preference(updated)
        except Exception:
            _logger.warning("upsert_notification_preference_failed", exc_info=True)
    return _notification_preference_model(updated)


@router.delete("/notifications/preferences/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification_preference(
    user_id: str,
    _: AuthPrincipal = Depends(require_admin),
    state: ControlPlaneState = Depends(get_control_plane_state),
    repository: Any | None = Depends(get_control_plane_repository),
) -> Response:
    try:
        deleted = state.delete_notification_preference(user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification preference not found")
    if repository is not None:
        try:
            repository.delete_notification_preference(user_id=user_id)
        except Exception:
            _logger.warning("delete_notification_preference_failed", exc_info=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/notifications/metrics", response_model=NotificationMetricsResponse)
def get_notification_metrics(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
) -> NotificationMetricsResponse:
    snapshot = state.notification_metrics_snapshot()
    totals = snapshot.get("totals", {})
    return NotificationMetricsResponse(
        totals=NotificationMetricsTotalsResponse(
            received_total=int(totals.get("received_total", 0)),
            filtered_total=int(totals.get("filtered_total", 0)),
            dispatched_total=int(totals.get("dispatched_total", 0)),
            delivered_total=int(totals.get("delivered_total", 0)),
            failed_total=int(totals.get("failed_total", 0)),
            retryable_total=int(totals.get("retryable_total", 0)),
            dlq_total=int(totals.get("dlq_total", 0)),
        ),
        suppression={str(key): int(value) for key, value in dict(snapshot.get("suppression", {})).items()},
        gateway_status={str(key): int(value) for key, value in dict(snapshot.get("gateway_status", {})).items()},
        retry_attempt_histogram={
            str(key): int(value) for key, value in dict(snapshot.get("retry_attempt_histogram", {})).items()
        },
        generated_at=str(snapshot.get("generated_at", "")),
    )


@router.get("/notifications/deliveries", response_model=NotificationDeliveryListResponse)
def list_notification_deliveries(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
    limit: int = Query(default=100, ge=1, le=500),
    gateway: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
) -> NotificationDeliveryListResponse:
    items = state.list_notification_delivery_logs(
        limit=limit,
        gateway=gateway,
        status=status_filter,
        severity=severity,
    )
    return NotificationDeliveryListResponse(items=[_notification_delivery_model(item) for item in items])


@router.get("/notifications/traces", response_model=NotificationTraceListResponse)
def list_notification_traces(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
    limit: int = Query(default=100, ge=1, le=500),
    trace_id: str | None = Query(default=None),
    stage: str | None = Query(default=None),
) -> NotificationTraceListResponse:
    items = state.list_notification_trace_spans(limit=limit, trace_id=trace_id, stage=stage)
    return NotificationTraceListResponse(items=[_notification_trace_model(item) for item in items])


def _order_model(item: ReconciliationOrder) -> OrderRecordResponse:
    return OrderRecordResponse(
        order_id=item.order_id,
        symbol=item.symbol,
        mode=ExecutionMode(item.mode.strip().upper()),
        status=item.status,
        requested_quantity=float(item.requested_quantity),
        filled_quantity=float(item.filled_quantity),
        average_price=float(item.average_price) if item.average_price is not None else None,
    )


def _position_model(item: PositionState) -> PositionRecordResponse:
    return PositionRecordResponse(
        mode=ExecutionMode(item.mode.strip().upper()),
        symbol=item.symbol,
        quantity=float(item.quantity),
        average_entry_price=float(item.average_entry_price),
        realized_pnl=float(item.realized_pnl),
        status=item.status,
        updated_at=item.updated_at,
    )


def _snapshot_model(item: PortfolioSnapshot) -> PortfolioSnapshotResponse:
    return PortfolioSnapshotResponse(
        snapshot_time=item.snapshot_time,
        mode=ExecutionMode(item.mode.strip().upper()),
        total_balance_usd=float(item.total_balance_usd),
        available_balance_usd=float(item.available_balance_usd),
        locked_balance_usd=float(item.locked_balance_usd),
        unrealized_pnl=float(item.unrealized_pnl),
        realized_pnl_total=float(item.realized_pnl_total),
    )


def _kline_model(item: dict[str, Any]) -> MarketKlineRecordResponse:
    return MarketKlineRecordResponse(
        time=str(item.get("time", "")),
        exchange=str(item.get("exchange", "")),
        symbol=str(item.get("symbol", "")),
        interval=str(item.get("interval", "")),
        open=float(item.get("open", 0.0) or 0.0),
        high=float(item.get("high", 0.0) or 0.0),
        low=float(item.get("low", 0.0) or 0.0),
        close=float(item.get("close", 0.0) or 0.0),
        volume=float(item.get("volume", 0.0) or 0.0),
        quote_volume=float(item.get("quote_volume", 0.0) or 0.0),
        trades=int(item.get("trades", 0) or 0),
    )


def _orderbook_snapshot_model(item: dict[str, Any]) -> OrderBookSnapshotResponse:
    return OrderBookSnapshotResponse(
        snapshot_time=str(item.get("snapshot_time", "")),
        exchange=str(item.get("exchange", "")),
        symbol=str(item.get("symbol", "")),
        best_bid=float(item.get("best_bid", 0.0) or 0.0),
        best_ask=float(item.get("best_ask", 0.0) or 0.0),
        spread_bps=float(item.get("spread_bps", 0.0) or 0.0),
        bids=_orderbook_level_models(item.get("bids")),
        asks=_orderbook_level_models(item.get("asks")),
    )


def _orderbook_level_models(levels: Any) -> list[OrderBookLevelResponse]:
    if not isinstance(levels, list):
        return []
    output: list[OrderBookLevelResponse] = []
    for level in levels:
        if not isinstance(level, dict):
            continue
        output.append(
            OrderBookLevelResponse(
                price=float(level.get("price", 0.0) or 0.0),
                amount=float(level.get("amount", 0.0) or 0.0),
            )
        )
    return output


def _signal_model(item: dict[str, Any]) -> SignalRecordResponse:
    return SignalRecordResponse(
        decision_id=str(item.get("decision_id", "")),
        trace_id=str(item.get("trace_id", "")),
        strategy_id=str(item.get("strategy_id", "")),
        mode=str(item.get("mode", "")),
        status=str(item.get("status", "")),
        action=str(item.get("action", "HOLD")),
        quantity=float(item.get("quantity", 0.0) or 0.0),
        confidence=float(item.get("confidence", 0.0) or 0.0),
        created_at=str(item.get("created_at", "")),
    )


def _trade_model(item: dict[str, Any]) -> TradeRecordResponse:
    return TradeRecordResponse(
        fill_id=str(item.get("fill_id", "")),
        order_id=str(item.get("order_id", "")),
        exchange_fill_id=str(item.get("exchange_fill_id", "")),
        exchange=str(item.get("exchange", "")),
        symbol=str(item.get("symbol", "")),
        mode=str(item.get("mode", "")),
        side=str(item.get("side", "")),
        quantity=float(item.get("quantity", 0.0) or 0.0),
        price=float(item.get("price", 0.0) or 0.0),
        fee=float(item.get("fee", 0.0) or 0.0),
        fee_currency=str(item.get("fee_currency", "")),
        filled_at=str(item.get("filled_at", "")),
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


def _news_item_model(item: NewsPanelItem) -> NewsItemResponse:
    return NewsItemResponse(
        news_id=item.news_id,
        source=item.source,
        title=item.title,
        url=item.url,
        published_at=item.published_at,
        symbol=item.symbol,
        topic=item.topic,
        relevance_score=item.relevance_score,
        sentiment_score=item.sentiment_score,
    )


def _news_summary_model(item: NewsPanelSummary) -> NewsSummaryResponse:
    return NewsSummaryResponse(
        summary_id=item.summary_id,
        symbol_scope=item.symbol_scope,
        window_start=item.window_start,
        window_end=item.window_end,
        summary_text=item.summary_text,
        generated_at=item.generated_at,
        source_count=len(item.source_news_ids),
        avg_sentiment=item.avg_sentiment,
    )


def _news_impact_model(item: NewsImpactRecord) -> NewsImpactRecordResponse:
    return NewsImpactRecordResponse(
        symbol=item.symbol,
        headline_count=item.headline_count,
        avg_sentiment=item.avg_sentiment,
        max_relevance=item.max_relevance,
        latest_published_at=item.latest_published_at,
        latest_summary=item.latest_summary,
    )


def _notification_preference_model(item: NotificationPreferenceRecord) -> NotificationPreferenceResponse:
    return NotificationPreferenceResponse(
        user_id=item.user_id,
        min_severity=item.min_severity,
        gateways=list(item.gateways),
        strategy_ids=list(item.strategy_ids),
        event_types=list(item.event_types),
        updated_at=item.updated_at,
        updated_by=item.updated_by,
    )


def _notification_delivery_model(item: NotificationDeliveryRecord) -> NotificationDeliveryRecordResponse:
    return NotificationDeliveryRecordResponse(
        notification_event_id=item.notification_event_id,
        trace_id=item.trace_id,
        decision_id=item.decision_id,
        event_type=item.event_type,
        severity=item.severity,
        gateway=item.gateway,
        delivery_status=item.delivery_status,
        attempt=item.attempt,
        detail=item.detail,
        logged_at=item.logged_at,
    )


def _notification_trace_model(item: NotificationTraceRecord) -> NotificationTraceRecordResponse:
    return NotificationTraceRecordResponse(
        notification_event_id=item.notification_event_id,
        trace_id=item.trace_id,
        decision_id=item.decision_id,
        stage=item.stage,
        status=item.status,
        latency_ms=item.latency_ms,
        gateway=item.gateway,
        attempt=item.attempt,
        started_at=item.started_at,
        completed_at=item.completed_at,
    )
