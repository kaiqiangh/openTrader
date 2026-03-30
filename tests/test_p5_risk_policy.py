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
        updated_at="2026-02-14T16:20:00Z",
    )


def _snapshot(*, total_balance_usd: float, realized_pnl_total: float) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        snapshot_time="2026-02-14T16:20:00Z",
        mode="REAL",
        total_balance_usd=total_balance_usd,
        available_balance_usd=total_balance_usd,
        locked_balance_usd=0.0,
        unrealized_pnl=0.0,
        realized_pnl_total=realized_pnl_total,
    )


def _engine() -> RiskPolicyEngine:
    config = RiskPolicyConfig(
        core=CoreRiskConfig(
            max_position_abs=2.0,
            max_symbol_notional_usd=400.0,
            max_leverage=2.0,
        ),
        guards=DrawdownDailyLossConfig(
            max_drawdown_pct=0.2,
            max_daily_loss_usd=300.0,
        ),
    )
    return RiskPolicyEngine(config=config, controls=RiskControlPlane())


def test_risk_policy_denies_when_core_rule_blocks() -> None:
    engine = _engine()

    result = engine.evaluate(
        order=ProposedOrder(mode="REAL", symbol="BTC/USDT", side="BUY", quantity=3.0, price=100.0),
        current_position=_position(quantity=0.0),
        snapshot=_snapshot(total_balance_usd=1_000.0, realized_pnl_total=0.0),
        peak_equity_usd=1_000.0,
        current_total_exposure_usd=0.0,
    )

    assert result.allowed is False
    assert "position_limit" in result.blocked_by


def test_risk_policy_denies_when_drawdown_guard_blocks() -> None:
    engine = _engine()

    result = engine.evaluate(
        order=ProposedOrder(mode="REAL", symbol="BTC/USDT", side="BUY", quantity=0.1, price=100.0),
        current_position=_position(quantity=0.0),
        snapshot=_snapshot(total_balance_usd=700.0, realized_pnl_total=0.0),
        peak_equity_usd=1_000.0,
        current_total_exposure_usd=0.0,
    )

    assert result.allowed is False
    assert "drawdown_limit" in result.blocked_by


def test_risk_policy_denies_when_kill_switch_enabled() -> None:
    controls = RiskControlPlane()
    controls.enable_kill_switch(
        reason="manual intervention",
        actor="ops",
        at=datetime(2026, 2, 14, 16, 40, tzinfo=timezone.utc),
    )

    config = RiskPolicyConfig(
        core=CoreRiskConfig(
            max_position_abs=2.0, max_symbol_notional_usd=10_000.0, max_leverage=5.0
        ),
        guards=DrawdownDailyLossConfig(max_drawdown_pct=0.5, max_daily_loss_usd=1_000.0),
    )
    engine = RiskPolicyEngine(config=config, controls=controls)

    result = engine.evaluate(
        order=ProposedOrder(mode="REAL", symbol="BTC/USDT", side="BUY", quantity=0.1, price=100.0),
        current_position=_position(quantity=0.0),
        snapshot=_snapshot(total_balance_usd=1_000.0, realized_pnl_total=0.0),
        peak_equity_usd=1_000.0,
        current_total_exposure_usd=0.0,
        now=datetime(2026, 2, 14, 16, 41, tzinfo=timezone.utc),
    )

    assert result.allowed is False
    assert "kill_switch" in result.blocked_by


def test_risk_policy_allows_when_all_checks_pass() -> None:
    engine = _engine()

    result = engine.evaluate(
        order=ProposedOrder(mode="REAL", symbol="BTC/USDT", side="BUY", quantity=0.2, price=100.0),
        current_position=_position(quantity=0.1),
        snapshot=_snapshot(total_balance_usd=1_000.0, realized_pnl_total=-50.0),
        peak_equity_usd=1_020.0,
        current_total_exposure_usd=10.0,
    )

    assert result.allowed is True
    assert result.blocked_by == ()
