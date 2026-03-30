from __future__ import annotations

from datetime import datetime, timezone

from services.oms.portfolio_snapshot import PortfolioSnapshot
from services.oms.position_engine import PositionState
from services.oms.risk_controls import RiskControlPlane
from services.oms.risk_guards import DrawdownDailyLossConfig
from services.oms.risk_observability import RiskObservabilityCollector
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


def _engine(*, controls: RiskControlPlane | None = None, sink: RiskObservabilityCollector | None = None) -> RiskPolicyEngine:
    return RiskPolicyEngine(
        config=RiskPolicyConfig(
            core=CoreRiskConfig(max_position_abs=1.0, max_symbol_notional_usd=200.0, max_leverage=2.0),
            guards=DrawdownDailyLossConfig(max_drawdown_pct=0.2, max_daily_loss_usd=200.0),
        ),
        controls=controls or RiskControlPlane(),
        observability_sink=sink,
    )


def test_risk_observability_tracks_allowed_and_denied_decisions() -> None:
    sink = RiskObservabilityCollector()
    engine = _engine(sink=sink)

    allowed = engine.evaluate(
        order=ProposedOrder(mode="REAL", symbol="BTC/USDT", side="BUY", quantity=0.2, price=100.0),
        current_position=_position(quantity=0.0),
        snapshot=_snapshot(total_balance_usd=1_000.0),
        peak_equity_usd=1_000.0,
        current_total_exposure_usd=0.0,
        trace_id="trace-1",
        decision_id="decision-1",
        strategy_id="strategy-a",
    )
    denied = engine.evaluate(
        order=ProposedOrder(mode="REAL", symbol="BTC/USDT", side="BUY", quantity=2.0, price=100.0),
        current_position=_position(quantity=0.0),
        snapshot=_snapshot(total_balance_usd=1_000.0),
        peak_equity_usd=1_000.0,
        current_total_exposure_usd=0.0,
        trace_id="trace-2",
        decision_id="decision-2",
        strategy_id="strategy-a",
    )

    assert allowed.allowed is True
    assert denied.allowed is False

    snapshot = sink.snapshot()
    assert snapshot["totals"]["evaluations_total"] == 2
    assert snapshot["totals"]["allowed_total"] == 1
    assert snapshot["totals"]["denied_total"] == 1
    assert snapshot["blocked_by"]["position_limit"] == 1

    events = sink.drain_events()
    assert [event.event_type for event in events] == ["risk.policy.allowed", "risk.policy.denied"]


def test_risk_observability_records_control_events_via_policy_drain() -> None:
    controls = RiskControlPlane(circuit_breaker_threshold=1, circuit_breaker_cooldown_seconds=30)
    sink = RiskObservabilityCollector()
    engine = _engine(controls=controls, sink=sink)

    controls.enable_kill_switch(
        reason="manual intervention",
        actor="ops",
        at=datetime(2026, 2, 14, 17, 10, tzinfo=timezone.utc),
    )

    drained = engine.drain_control_events()
    assert [event.event_type for event in drained] == ["risk.kill_switch.enabled"]

    snapshot = sink.snapshot()
    assert snapshot["totals"]["control_events_total"] == 1

    events = sink.drain_events()
    assert events[-1].event_type == "risk.control.risk.kill_switch.enabled"
    assert events[-1].severity == "CRITICAL"
