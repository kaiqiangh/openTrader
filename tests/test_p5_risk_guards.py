from __future__ import annotations

from services.oms.portfolio_snapshot import PortfolioSnapshot
from services.oms.risk_guards import DrawdownDailyLossConfig, DrawdownDailyLossGuardEngine


def _snapshot(*, total_balance_usd: float, realized_pnl_today: float) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        snapshot_time="2026-02-14T16:20:00Z",
        mode="REAL",
        total_balance_usd=total_balance_usd,
        available_balance_usd=total_balance_usd,
        locked_balance_usd=0.0,
        unrealized_pnl=0.0,
        realized_pnl_today=realized_pnl_today,
    )


def test_drawdown_guard_blocks_when_threshold_breached() -> None:
    engine = DrawdownDailyLossGuardEngine(
        config=DrawdownDailyLossConfig(max_drawdown_pct=0.2, max_daily_loss_usd=1_000.0)
    )

    result = engine.evaluate(
        snapshot=_snapshot(total_balance_usd=700.0, realized_pnl_today=0.0),
        peak_equity_usd=1_000.0,
    )

    assert result.allowed is False
    assert "drawdown_limit" in result.blocked_by


def test_daily_loss_guard_blocks_when_threshold_breached() -> None:
    engine = DrawdownDailyLossGuardEngine(
        config=DrawdownDailyLossConfig(max_drawdown_pct=0.5, max_daily_loss_usd=300.0)
    )

    result = engine.evaluate(
        snapshot=_snapshot(total_balance_usd=1_000.0, realized_pnl_today=-350.0),
        peak_equity_usd=1_100.0,
    )

    assert result.allowed is False
    assert "daily_loss_limit" in result.blocked_by


def test_drawdown_and_daily_loss_guards_allow_when_in_bounds() -> None:
    engine = DrawdownDailyLossGuardEngine(
        config=DrawdownDailyLossConfig(max_drawdown_pct=0.3, max_daily_loss_usd=500.0)
    )

    result = engine.evaluate(
        snapshot=_snapshot(total_balance_usd=980.0, realized_pnl_today=-120.0),
        peak_equity_usd=1_000.0,
    )

    assert result.allowed is True
    assert result.blocked_by == ()
