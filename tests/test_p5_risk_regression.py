from __future__ import annotations

from datetime import datetime, timezone

from services.oms.portfolio_snapshot import PortfolioSnapshot
from services.oms.position_engine import PositionState
from services.oms.risk_controls import RiskControlPlane
from services.oms.risk_guards import DrawdownDailyLossConfig
from services.oms.risk_policy import RiskPolicyConfig, RiskPolicyEngine
from services.oms.risk_rules import CoreRiskConfig, ProposedOrder


def _position(*, quantity: float) -> PositionState:
    return PositionState(
        mode="REAL",
        symbol="BTC/USDT",
        quantity=quantity,
        average_entry_price=100.0,
        realized_pnl=0.0,
        status="OPEN" if abs(quantity) > 1e-9 else "CLOSED",
        updated_at="2026-02-14T17:00:00Z",
    )


def _snapshot(*, total_balance_usd: float, realized_pnl_total: float = 0.0) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        snapshot_time="2026-02-14T17:00:00Z",
        mode="REAL",
        total_balance_usd=total_balance_usd,
        available_balance_usd=total_balance_usd,
        locked_balance_usd=0.0,
        unrealized_pnl=0.0,
        realized_pnl_total=realized_pnl_total,
    )


def _engine(*, controls: RiskControlPlane | None = None) -> RiskPolicyEngine:
    return RiskPolicyEngine(
        config=RiskPolicyConfig(
            core=CoreRiskConfig(max_position_abs=1.0, max_symbol_notional_usd=100.0, max_leverage=1.5),
            guards=DrawdownDailyLossConfig(max_drawdown_pct=0.2, max_daily_loss_usd=100.0),
        ),
        controls=controls or RiskControlPlane(),
    )


def test_regression_allows_at_exact_position_and_notional_boundaries() -> None:
    engine = _engine()

    result = engine.evaluate(
        order=ProposedOrder(mode="REAL", symbol="BTC/USDT", side="BUY", quantity=0.5, price=100.0),
        current_position=_position(quantity=0.5),
        snapshot=_snapshot(total_balance_usd=500.0),
        peak_equity_usd=500.0,
        current_total_exposure_usd=50.0,
    )

    assert result.allowed is True


def test_regression_blocks_when_equity_is_zero_and_exposure_positive() -> None:
    engine = _engine()

    result = engine.evaluate(
        order=ProposedOrder(mode="REAL", symbol="BTC/USDT", side="BUY", quantity=0.1, price=100.0),
        current_position=_position(quantity=0.0),
        snapshot=_snapshot(total_balance_usd=0.0),
        peak_equity_usd=100.0,
        current_total_exposure_usd=0.0,
    )

    assert result.allowed is False
    assert "leverage_limit" in result.blocked_by


def test_regression_sell_reducing_exposure_passes_under_leverage_limit() -> None:
    engine = _engine()

    result = engine.evaluate(
        order=ProposedOrder(mode="REAL", symbol="BTC/USDT", side="SELL", quantity=0.4, price=100.0),
        current_position=_position(quantity=1.0),
        snapshot=_snapshot(total_balance_usd=100.0),
        peak_equity_usd=100.0,
        current_total_exposure_usd=100.0,
    )

    assert result.allowed is True


def test_regression_circuit_breaker_blocks_then_auto_resets_after_cooldown() -> None:
    controls = RiskControlPlane(circuit_breaker_threshold=1, circuit_breaker_cooldown_seconds=5)
    engine = _engine(controls=controls)

    controls.record_failure(
        reason="exchange error",
        actor="worker",
        at=datetime(2026, 2, 14, 17, 20, tzinfo=timezone.utc),
    )

    blocked = engine.evaluate(
        order=ProposedOrder(mode="REAL", symbol="BTC/USDT", side="BUY", quantity=0.1, price=100.0),
        current_position=_position(quantity=0.0),
        snapshot=_snapshot(total_balance_usd=1_000.0),
        peak_equity_usd=1_000.0,
        current_total_exposure_usd=0.0,
        now=datetime(2026, 2, 14, 17, 20, 1, tzinfo=timezone.utc),
    )
    assert blocked.allowed is False
    assert "circuit_breaker" in blocked.blocked_by

    unblocked = engine.evaluate(
        order=ProposedOrder(mode="REAL", symbol="BTC/USDT", side="BUY", quantity=0.1, price=100.0),
        current_position=_position(quantity=0.0),
        snapshot=_snapshot(total_balance_usd=1_000.0),
        peak_equity_usd=1_000.0,
        current_total_exposure_usd=0.0,
        now=datetime(2026, 2, 14, 17, 20, 6, tzinfo=timezone.utc),
    )
    assert unblocked.allowed is True


def test_regression_dedupes_blocked_reason_codes() -> None:
    controls = RiskControlPlane(circuit_breaker_threshold=1, circuit_breaker_cooldown_seconds=30)
    controls.enable_kill_switch(
        reason="manual intervention",
        actor="ops",
        at=datetime(2026, 2, 14, 17, 25, tzinfo=timezone.utc),
    )
    controls.record_failure(
        reason="critical risk event",
        actor="risk",
        at=datetime(2026, 2, 14, 17, 25, 1, tzinfo=timezone.utc),
    )
    engine = _engine(controls=controls)

    result = engine.evaluate(
        order=ProposedOrder(mode="REAL", symbol="BTC/USDT", side="BUY", quantity=2.0, price=100.0),
        current_position=_position(quantity=0.0),
        snapshot=_snapshot(total_balance_usd=1_000.0),
        peak_equity_usd=1_000.0,
        current_total_exposure_usd=0.0,
        now=datetime(2026, 2, 14, 17, 25, 2, tzinfo=timezone.utc),
    )

    assert result.allowed is False
    assert len(set(result.blocked_by)) == len(result.blocked_by)
    assert "kill_switch" in result.blocked_by
    assert "circuit_breaker" in result.blocked_by
    assert "position_limit" in result.blocked_by
