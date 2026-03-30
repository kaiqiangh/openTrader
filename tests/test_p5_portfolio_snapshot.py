from __future__ import annotations

import pytest

from services.oms.portfolio_snapshot import PortfolioSnapshotEngine, PortfolioSnapshotEngineError
from services.oms.position_engine import PositionState


def test_portfolio_snapshot_engine_computes_total_and_unrealized_pnl() -> None:
    engine = PortfolioSnapshotEngine()
    positions = (
        PositionState(
            mode="MOCK",
            symbol="BTC/USDT",
            quantity=1.0,
            average_entry_price=100.0,
            realized_pnl=10.0,
            status="OPEN",
            updated_at="2026-02-14T16:00:00Z",
        ),
        PositionState(
            mode="MOCK",
            symbol="ETH/USDT",
            quantity=-2.0,
            average_entry_price=50.0,
            realized_pnl=-3.0,
            status="OPEN",
            updated_at="2026-02-14T16:00:00Z",
        ),
    )

    snapshot = engine.build_snapshot(
        mode="MOCK",
        available_balance_usd=1000.0,
        locked_balance_usd=200.0,
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
            quantity=0.0,
            average_entry_price=0.0,
            realized_pnl=999.0,
            status="CLOSED",
            updated_at="2026-02-14T16:00:00Z",
        ),
    )

    snapshot = engine.build_snapshot(
        mode="REAL",
        available_balance_usd=500.0,
        locked_balance_usd=0.0,
        positions=positions,
        mark_prices={},
        realized_pnl_total=12.5,
    )

    assert snapshot.realized_pnl_total == pytest.approx(12.5)


def test_portfolio_snapshot_engine_requires_mark_price_for_open_positions() -> None:
    engine = PortfolioSnapshotEngine()
    positions = (
        PositionState(
            mode="REAL",
            symbol="ETH/USDT",
            quantity=1.0,
            average_entry_price=2000.0,
            realized_pnl=0.0,
            status="OPEN",
            updated_at="2026-02-14T16:00:00Z",
        ),
    )

    with pytest.raises(PortfolioSnapshotEngineError):
        engine.build_snapshot(
            mode="REAL",
            available_balance_usd=100.0,
            locked_balance_usd=0.0,
            positions=positions,
            mark_prices={},
        )
