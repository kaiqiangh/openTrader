from __future__ import annotations

import pytest

from services.oms.position_engine import PositionState
from services.oms.risk_rules import CoreRiskConfig, CoreRiskRuleEngine, ProposedOrder


def _position(*, quantity: float = 0.0, average_entry_price: float = 100.0) -> PositionState:
    return PositionState(
        mode="REAL",
        symbol="BTC/USDT",
        quantity=quantity,
        average_entry_price=average_entry_price,
        realized_pnl=0.0,
        status="OPEN" if abs(quantity) > 1e-9 else "CLOSED",
        updated_at="2026-02-14T16:20:00Z",
    )


def test_core_risk_rules_block_when_projected_notional_exceeds_limit() -> None:
    engine = CoreRiskRuleEngine(
        config=CoreRiskConfig(
            max_position_abs=5.0,
            max_symbol_notional_usd=150.0,
            max_leverage=5.0,
        )
    )

    result = engine.evaluate(
        order=ProposedOrder(mode="REAL", symbol="BTC/USDT", side="BUY", quantity=1.0, price=200.0),
        current_position=_position(quantity=0.0),
        account_equity_usd=1_000.0,
        current_total_exposure_usd=0.0,
    )

    assert result.allowed is False
    assert "symbol_notional_limit" in result.blocked_by


def test_core_risk_rules_block_when_projected_leverage_exceeds_limit() -> None:
    engine = CoreRiskRuleEngine(
        config=CoreRiskConfig(
            max_position_abs=10.0,
            max_symbol_notional_usd=5_000.0,
            max_leverage=1.2,
        )
    )

    result = engine.evaluate(
        order=ProposedOrder(mode="REAL", symbol="BTC/USDT", side="BUY", quantity=0.5, price=100.0),
        current_position=_position(quantity=0.0),
        account_equity_usd=30.0,
        current_total_exposure_usd=0.0,
    )

    assert result.allowed is False
    assert "leverage_limit" in result.blocked_by


def test_core_risk_rules_block_when_projected_position_exceeds_limit() -> None:
    engine = CoreRiskRuleEngine(
        config=CoreRiskConfig(
            max_position_abs=1.0,
            max_symbol_notional_usd=100_000.0,
            max_leverage=10.0,
        )
    )

    result = engine.evaluate(
        order=ProposedOrder(mode="REAL", symbol="BTC/USDT", side="BUY", quantity=0.3, price=100.0),
        current_position=_position(quantity=0.9),
        account_equity_usd=10_000.0,
        current_total_exposure_usd=90.0,
    )

    assert result.allowed is False
    assert "position_limit" in result.blocked_by


def test_core_risk_rules_allow_when_all_limits_are_respected() -> None:
    engine = CoreRiskRuleEngine(
        config=CoreRiskConfig(
            max_position_abs=2.0,
            max_symbol_notional_usd=1_000.0,
            max_leverage=3.0,
        )
    )

    result = engine.evaluate(
        order=ProposedOrder(mode="REAL", symbol="BTC/USDT", side="BUY", quantity=0.25, price=120.0),
        current_position=_position(quantity=0.5),
        account_equity_usd=500.0,
        current_total_exposure_usd=60.0,
    )

    assert result.allowed is True
    assert result.blocked_by == ()
    assert result.projected_position_qty == pytest.approx(0.75)
    assert result.projected_symbol_notional_usd == pytest.approx(90.0)
