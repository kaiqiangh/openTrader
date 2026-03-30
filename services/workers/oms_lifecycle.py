"""OMS lifecycle worker runner with reconciliation helpers."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from services.oms.fill_reconciliation import FillReconciliationEngine, LifecycleEvent, ReconciliationOrder
from services.oms.portfolio_snapshot import PortfolioSnapshotEngine
from services.oms.position_engine import PositionEngine, PositionFill, PositionState
from services.workers.helpers import _resolve_requested_quantity, _utc_now_iso
from services.workers.runtime_persistence import SQLAlchemyRuntimeOMSStateStore


def _to_lifecycle_event(envelope: Mapping[str, Any]) -> LifecycleEvent:
    from decimal import Decimal

    event_type = str(envelope.get("event_type", ""))
    payload = envelope.get("payload")
    if not isinstance(payload, Mapping):
        return LifecycleEvent(event_type=event_type)
    if event_type not in {"oms.order.filled", "oms.order.partially_filled"}:
        return LifecycleEvent(event_type=event_type)
    order_id = str(payload.get("order_id", ""))
    if not order_id:
        return LifecycleEvent(event_type=event_type)
    fill_price = payload.get("fill_price", payload.get("price", 0.0))
    fill = PositionFill(
        order_id=order_id,
        mode=str(payload.get("mode", "MOCK")),
        symbol=str(payload.get("symbol", "")),
        side=str(payload.get("action", "BUY")),
        quantity=Decimal(str(abs(float(payload.get("quantity", 0.0) or 0.0)))),
        price=Decimal(str(float(fill_price or 0.0))),
        fee=Decimal(str(float(payload.get("fee_paid", payload.get("fee", 0.0)) or 0.0))),
        filled_at=str(envelope.get("emitted_at", _utc_now_iso())),
    )
    return LifecycleEvent(
        event_type=event_type,
        fill=_position_fill_to_reconciliation_fill(fill=fill),
    )


def _position_fill_to_reconciliation_fill(*, fill: PositionFill):
    from services.oms.fill_reconciliation import ReconciliationFill

    return ReconciliationFill(
        fill_id=f"fill:{fill.order_id}:{fill.filled_at or _utc_now_iso()}",
        order_id=fill.order_id,
        quantity=abs(fill.quantity),
        price=fill.price,
        fee=fill.fee,
        source="runtime_worker",
    )


class OMSLifecycleWorkerRunner:
    """Stateful OMS loop for reconciliation, position updates, and snapshots."""

    def __init__(
        self,
        *,
        broker: Any,
        base_balance_usd: float,
        state_store: SQLAlchemyRuntimeOMSStateStore | None = None,
    ) -> None:
        self.broker = broker
        self.base_balance_usd = base_balance_usd
        self.state_store = state_store
        self.reconciliation = FillReconciliationEngine()
        self.position_engine = PositionEngine()
        self.snapshot_engine = PortfolioSnapshotEngine()
        self._orders: dict[str, ReconciliationOrder] = {}
        self._lifecycle_events: dict[str, list[LifecycleEvent]] = {}
        self._positions: dict[str, PositionState] = {}
        self._mark_prices: dict[str, float] = {}
        self._last_activity: dict[str, Any] = {}

    async def run_once(self, *, timeout_seconds: float) -> bool:
        envelope = await self.broker.consume(
            queue_name="oms.events.order_updates",
            timeout_seconds=timeout_seconds,
        )
        if envelope is None:
            return False

        payload = envelope.get("payload")
        if not isinstance(payload, Mapping):
            return False
        order_id = str(payload.get("order_id", "")).strip()
        symbol = str(payload.get("symbol", "")).strip()
        mode = str(payload.get("mode", "MOCK")).strip().upper() or "MOCK"
        if not order_id or not symbol:
            return False

        requested_quantity = _resolve_requested_quantity(payload.get("quantity"))
        if self.state_store is None:
            existing_order = self._orders.get(
                order_id,
                ReconciliationOrder(
                    order_id=order_id,
                    symbol=symbol,
                    mode=mode,
                    requested_quantity=requested_quantity,
                ),
            )
        else:
            existing_order = self.state_store.get_order(order_id=order_id) or ReconciliationOrder(
                order_id=order_id,
                symbol=symbol,
                mode=mode,
                requested_quantity=requested_quantity,
            )
        lifecycle_event = _to_lifecycle_event(envelope)
        if self.state_store is None:
            events_for_order = self._lifecycle_events.setdefault(order_id, [])
            events_for_order.append(lifecycle_event)
        else:
            self.state_store.append_lifecycle_event(order_id=order_id, event=lifecycle_event)
            events_for_order = list(self.state_store.load_lifecycle_events(order_id=order_id))

        reconciliation = self.reconciliation.reconcile(
            order=existing_order,
            lifecycle_events=tuple(events_for_order),
            exchange_snapshot=None,
        )
        updated_order = ReconciliationOrder(
            order_id=order_id,
            symbol=symbol,
            mode=mode,
            requested_quantity=existing_order.requested_quantity,
            status=reconciliation.status,
            filled_quantity=reconciliation.filled_quantity,
            average_price=reconciliation.average_price,
        )
        if self.state_store is None:
            self._orders[order_id] = updated_order
        else:
            self.state_store.upsert_order(updated_order)

        if lifecycle_event.fill is not None:
            fill = lifecycle_event.fill
            side = str(payload.get("action", "BUY")).upper()
            if self.state_store is None:
                current = self._positions.get(symbol)
            else:
                current = self.state_store.get_position(mode=mode, symbol=symbol)
            position_update = self.position_engine.apply_fill(
                position=current,
                fill=PositionFill(
                    order_id=order_id,
                    mode=mode,
                    symbol=symbol,
                    side=side,
                    quantity=fill.quantity,
                    price=fill.price,
                    fee=fill.fee,
                    filled_at=str(envelope.get("emitted_at", _utc_now_iso())),
                ),
            )
            if self.state_store is None:
                self._positions[symbol] = position_update.current
                self._mark_prices[symbol] = fill.price
            else:
                self.state_store.upsert_position(position_update.current)
                self.state_store.upsert_mark_price(mode=mode, symbol=symbol, mark_price=fill.price)

        if self.state_store is None:
            positions = tuple(self._positions.values())
            mark_prices = dict(self._mark_prices)
        else:
            positions = self.state_store.list_positions(mode=mode)
            mark_prices = self.state_store.load_mark_prices(mode=mode)

        snapshot = self.snapshot_engine.build_snapshot(
            mode=mode,
            available_balance_usd=Decimal(str(self.base_balance_usd)),
            locked_balance_usd=Decimal("0"),
            positions=positions,
            mark_prices=mark_prices,
            realized_pnl_total=sum(position.realized_pnl for position in positions),
        )
        if self.state_store is not None:
            self.state_store.insert_portfolio_snapshot(snapshot)
        self._last_activity = {
            "event": str(envelope.get("event_type", "")),
            "trace_id": str(envelope.get("trace_id", "")),
            "decision_id": str(envelope.get("decision_id", "")),
            "order_id": order_id,
            "symbol": symbol,
            "mode": mode,
            "order_status": updated_order.status,
            "filled_quantity": updated_order.filled_quantity,
            "average_price": updated_order.average_price,
            "positions_total": len(positions),
            "portfolio_total_balance_usd": snapshot.total_balance_usd,
            "portfolio_unrealized_pnl": snapshot.unrealized_pnl,
            "portfolio_realized_pnl_total": snapshot.realized_pnl_total,
        }
        return True

    def activity_snapshot(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tracked_orders_total": len(self._orders) if self.state_store is None else None,
            "positions_total": len(self._positions) if self.state_store is None else None,
        }
        if self._last_activity:
            payload["last_activity"] = dict(self._last_activity)
        return payload
