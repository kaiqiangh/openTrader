from __future__ import annotations

from services.oms.fill_reconciliation import (
    ExchangeOrderSnapshot,
    FillReconciliationEngine,
    LifecycleEvent,
    ReconciliationFill,
    ReconciliationOrder,
)


def test_reconcile_uses_exchange_fallback_for_missing_queue_fills() -> None:
    engine = FillReconciliationEngine()
    order = ReconciliationOrder(
        order_id="order-1",
        symbol="BTC/USDT",
        mode="REAL",
        requested_quantity=1.0,
        status="OPEN",
        filled_quantity=0.4,
        average_price=100.0,
    )

    result = engine.reconcile(
        order=order,
        lifecycle_events=(
            LifecycleEvent(
                event_type="oms.order.partially_filled",
                fill=ReconciliationFill(
                    fill_id="fill-1",
                    order_id="order-1",
                    quantity=0.4,
                    price=100.0,
                    fee=0.1,
                ),
            ),
        ),
        exchange_snapshot=ExchangeOrderSnapshot(
            status="FILLED",
            filled_quantity=1.0,
            average_price=101.2,
            fills=(
                ReconciliationFill(
                    fill_id="fill-2",
                    order_id="order-1",
                    quantity=0.6,
                    price=102.0,
                    fee=0.15,
                    source="exchange",
                ),
            ),
        ),
    )

    assert result.used_exchange_fallback is True
    assert result.status == "FILLED"
    assert result.filled_quantity == 1.0
    assert len(result.fills) == 2
    assert result.changed is True


def test_reconcile_keeps_terminal_queue_status_when_snapshot_has_no_new_fill() -> None:
    engine = FillReconciliationEngine()
    order = ReconciliationOrder(
        order_id="order-2",
        symbol="BTC/USDT",
        mode="REAL",
        requested_quantity=1.0,
        status="CANCELED",
        filled_quantity=0.0,
        average_price=None,
    )

    result = engine.reconcile(
        order=order,
        lifecycle_events=(LifecycleEvent(event_type="oms.order.canceled"),),
        exchange_snapshot=ExchangeOrderSnapshot(
            status="OPEN",
            filled_quantity=0.0,
            average_price=None,
            fills=(),
        ),
    )

    assert result.status == "CANCELED"
    assert result.used_exchange_fallback is False
    assert result.changed is False


def test_reconcile_dedupes_duplicate_fill_ids() -> None:
    engine = FillReconciliationEngine()
    order = ReconciliationOrder(
        order_id="order-3",
        symbol="ETH/USDT",
        mode="MOCK",
        requested_quantity=1.0,
        status="OPEN",
        filled_quantity=0.0,
        average_price=None,
    )

    duplicate = ReconciliationFill(
        fill_id="fill-dup",
        order_id="order-3",
        quantity=0.2,
        price=2000.0,
    )

    result = engine.reconcile(
        order=order,
        lifecycle_events=(
            LifecycleEvent(event_type="oms.order.partially_filled", fill=duplicate),
            LifecycleEvent(event_type="oms.order.partially_filled", fill=duplicate),
            LifecycleEvent(
                event_type="oms.order.partially_filled",
                fill=ReconciliationFill(
                    fill_id="fill-4",
                    order_id="order-3",
                    quantity=0.3,
                    price=2010.0,
                ),
            ),
        ),
    )

    assert result.status == "PARTIALLY_FILLED"
    assert len(result.fills) == 2
    assert result.filled_quantity == 0.5
    assert result.average_price is not None
    assert result.average_price > 2000.0
    assert result.changed is True


def test_reconcile_marks_unchanged_when_order_snapshot_matches() -> None:
    engine = FillReconciliationEngine()
    order = ReconciliationOrder(
        order_id="order-4",
        symbol="ETH/USDT",
        mode="MOCK",
        requested_quantity=0.5,
        status="PARTIALLY_FILLED",
        filled_quantity=0.2,
        average_price=2000.0,
    )

    result = engine.reconcile(order=order)

    assert result.status == "PARTIALLY_FILLED"
    assert result.filled_quantity == 0.2
    assert result.average_price == 2000.0
    assert result.changed is False
