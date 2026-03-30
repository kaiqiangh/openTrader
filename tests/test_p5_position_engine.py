from __future__ import annotations

from decimal import Decimal

import pytest

from services.oms.position_engine import PositionEngine, PositionEngineError, PositionFill, PositionState


def test_position_engine_opens_long_position_from_first_buy_fill() -> None:
    engine = PositionEngine()

    update = engine.apply_fill(
        position=None,
        fill=PositionFill(
            order_id="order-1",
            mode="MOCK",
            symbol="BTC/USDT",
            side="BUY",
            quantity=Decimal("0.5"),
            price=Decimal("100.0"),
            fee=Decimal("0.02"),
        ),
    )

    assert update.previous.quantity == Decimal("0")
    assert update.current.quantity == Decimal("0.5")
    assert update.current.average_entry_price == Decimal("100.0")
    assert update.current.status == "OPEN"
    assert update.current.realized_pnl == pytest.approx(Decimal("-0.02"))


def test_position_engine_realizes_pnl_on_partial_close() -> None:
    engine = PositionEngine()
    position = PositionState(
        mode="REAL",
        symbol="ETH/USDT",
        quantity=Decimal("1.0"),
        average_entry_price=Decimal("2000.0"),
        realized_pnl=Decimal("0"),
        status="OPEN",
        updated_at="2026-02-14T16:00:00Z",
    )

    update = engine.apply_fill(
        position=position,
        fill=PositionFill(
            order_id="order-2",
            mode="REAL",
            symbol="ETH/USDT",
            side="SELL",
            quantity=Decimal("0.4"),
            price=Decimal("2100.0"),
            fee=Decimal("1.0"),
        ),
    )

    assert update.current.quantity == pytest.approx(Decimal("0.6"))
    assert update.current.average_entry_price == pytest.approx(Decimal("2000.0"))
    assert update.realized_pnl_delta == pytest.approx(Decimal(str((2100.0 - 2000.0) * 0.4 - 1.0)))
    assert update.current.realized_pnl == pytest.approx(update.realized_pnl_delta)


def test_position_engine_handles_flip_from_long_to_short() -> None:
    engine = PositionEngine()
    position = PositionState(
        mode="REAL",
        symbol="BTC/USDT",
        quantity=Decimal("0.5"),
        average_entry_price=Decimal("100.0"),
        realized_pnl=Decimal("3.0"),
        status="OPEN",
        updated_at="2026-02-14T16:00:00Z",
    )

    update = engine.apply_fill(
        position=position,
        fill=PositionFill(
            order_id="order-3",
            mode="REAL",
            symbol="BTC/USDT",
            side="SELL",
            quantity=Decimal("0.8"),
            price=Decimal("90.0"),
            fee=Decimal("0.5"),
        ),
    )

    assert update.current.quantity == pytest.approx(Decimal("-0.3"))
    assert update.current.average_entry_price == pytest.approx(Decimal("90.0"))
    assert update.current.status == "OPEN"
    assert update.realized_pnl_delta == pytest.approx(Decimal(str((90.0 - 100.0) * 0.5 - 0.5)))
    assert update.current.realized_pnl == pytest.approx(Decimal("3.0") + update.realized_pnl_delta)


def test_position_engine_rejects_symbol_mismatch() -> None:
    engine = PositionEngine()
    position = PositionState(
        mode="MOCK",
        symbol="BTC/USDT",
        quantity=Decimal("1.0"),
        average_entry_price=Decimal("100.0"),
        realized_pnl=Decimal("0"),
        status="OPEN",
        updated_at="2026-02-14T16:00:00Z",
    )

    with pytest.raises(PositionEngineError):
        engine.apply_fill(
            position=position,
            fill=PositionFill(
                order_id="order-4",
                mode="MOCK",
                symbol="ETH/USDT",
                side="BUY",
                quantity=Decimal("0.2"),
                price=Decimal("100.0"),
            ),
        )
