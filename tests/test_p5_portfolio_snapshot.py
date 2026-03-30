from __future__ import annotations

from decimal import Decimal

import pytest

from services.oms.portfolio_snapshot import PortfolioSnapshotEngine, PortfolioSnapshotEngineError
from services.oms.position_engine import PositionState


def test_portfolio_snapshot_engine_computes_total_and_unrealized_pnl() -> None:
    engine = PortfolioSnapshotEngine()
    positions = (
        PositionState(
            mode="MOCK",
            symbol="BTC/USDT",
            quantity=Decimal("1.0"),
            average_entry_price=Decimal("100.0"),
            realized_pnl=Decimal("10.0"),
            status="OPEN",
            updated_at="2026-02-14T16:00:00Z",
        ),
        PositionState(
            mode="MOCK",
            symbol="ETH/USDT",
            quantity=Decimal("-2.0"),
            average_entry_price=Decimal("50.0"),
            realized_pnl=Decimal("-3.0"),
            status="OPEN",
            updated_at="2026-02-14T16:00:00Z",
        ),
    )

    snapshot = engine.build_snapshot(
        mode="MOCK",
        available_balance_usd=Decimal("1000.0"),
        locked_balance_usd=Decimal("200.0"),
        positions=positions,
        mark_prices={"BTC/USDT": 110.0, "ETH/USDT": 40.0},
    )

    expected_unrealized = (110.0 - 100.0) * 1.0 + (40.0 - 50.0) * -2.0
    assert snapshot.unrealized_pnl == pytest.approx(expected_unrealized)
    assert snapshot.total_balance_usd == pytest.approx(1000.0 + 200.0 + expected_unrealized)
    assert snapshot.realized_pnl_total == pytest.approx(7.0)
    assert snapshot.mode == "MOCK"


def test_portfolio_snapshot_engine_allows_realized_override() -> None:
    engine = PortfolioSnapshotEngine()
    positions = (
        PositionState(
            mode="REAL",
            symbol="BTC/USDT",
            quantity=Decimal("0"),
            average_entry_price=Decimal("0"),
            realized_pnl=Decimal("999.0"),
            status="CLOSED",
            updated_at="2026-02-14T16:00:00Z",
        ),
    )

    snapshot = engine.build_snapshot(
        mode="REAL",
        available_balance_usd=Decimal("500.0"),
        locked_balance_usd=Decimal("0"),
        positions=positions,
        mark_prices={},
        realized_pnl_total=Decimal("12.5"),
    )

    assert snapshot.realized_pnl_total == pytest.approx(12.5)


def test_portfolio_snapshot_engine_requires_mark_price_for_open_positions() -> None:
    engine = PortfolioSnapshotEngine()
    positions = (
        PositionState(
            mode="REAL",
            symbol="ETH/USDT",
            quantity=Decimal("1.0"),
            average_entry_price=Decimal("2000.0"),
            realized_pnl=Decimal("0"),
            status="OPEN",
            updated_at="2026-02-14T16:00:00Z",
        ),
    )

    with pytest.raises(PortfolioSnapshotEngineError):
        engine.build_snapshot(
            mode="REAL",
            available_balance_usd=Decimal("100.0"),
            locked_balance_usd=Decimal("0"),
            positions=positions,
            mark_prices={},
        )
