"""Tests for drawdown protection and daily loss limits in risk rules."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.oms.risk_rules import (
    CoreRiskCheck,
    CoreRiskConfig,
    CoreRiskEvaluation,
    CoreRiskRuleEngine,
    CoreRiskRuleError,
    ProposedOrder,
)


def _make_order(**overrides: object) -> ProposedOrder:
    defaults = dict(mode="MOCK", symbol="BTC/USDT", side="BUY", quantity=1.0, price=50000.0)
    defaults.update(overrides)
    return ProposedOrder(**defaults)  # type: ignore[arg-type]


def _make_config(**overrides: object) -> CoreRiskConfig:
    defaults = dict(
        max_position_abs=100.0,
        max_symbol_notional_usd=1_000_000.0,
        max_leverage=10.0,
        max_daily_loss_usd=5000.0,
        max_drawdown_pct=0.10,
    )
    defaults.update(overrides)
    return CoreRiskConfig(**defaults)  # type: ignore[arg-type]


class TestDailyLossLimit:
    def test_passes_when_pnl_positive(self) -> None:
        engine = CoreRiskRuleEngine(config=_make_config())
        result = engine.evaluate(
            order=_make_order(),
            current_position=None,
            account_equity_usd=100_000.0,
            current_total_exposure_usd=0.0,
            realized_pnl_today=1000.0,
        )
        assert result.allowed is True
        check = _find_check(result.checks, "daily_loss_limit")
        assert check is not None
        assert check.passed is True

    def test_passes_when_pnl_within_limit(self) -> None:
        engine = CoreRiskRuleEngine(config=_make_config(max_daily_loss_usd=5000.0))
        result = engine.evaluate(
            order=_make_order(),
            current_position=None,
            account_equity_usd=100_000.0,
            current_total_exposure_usd=0.0,
            realized_pnl_today=-3000.0,
        )
        assert result.allowed is True

    def test_blocks_when_daily_loss_exceeds_limit(self) -> None:
        engine = CoreRiskRuleEngine(config=_make_config(max_daily_loss_usd=5000.0))
        result = engine.evaluate(
            order=_make_order(),
            current_position=None,
            account_equity_usd=100_000.0,
            current_total_exposure_usd=0.0,
            realized_pnl_today=-6000.0,
        )
        assert result.allowed is False
        assert "daily_loss_limit" in result.blocked_by

    def test_skips_when_disabled(self) -> None:
        engine = CoreRiskRuleEngine(config=_make_config(max_daily_loss_usd=0.0))
        result = engine.evaluate(
            order=_make_order(),
            current_position=None,
            account_equity_usd=100_000.0,
            current_total_exposure_usd=0.0,
            realized_pnl_today=-999999.0,
        )
        assert result.allowed is True
        check = _find_check(result.checks, "daily_loss_limit")
        assert check is None


class TestMaxDrawdown:
    def test_passes_when_within_drawdown_limit(self) -> None:
        engine = CoreRiskRuleEngine(config=_make_config(max_drawdown_pct=0.10))
        result = engine.evaluate(
            order=_make_order(),
            current_position=None,
            account_equity_usd=95_000.0,  # 5% drawdown from 100k peak
            current_total_exposure_usd=0.0,
            peak_equity_usd=100_000.0,
        )
        assert result.allowed is True
        check = _find_check(result.checks, "max_drawdown")
        assert check is not None
        assert check.passed is True

    def test_blocks_when_drawdown_exceeds_limit(self) -> None:
        engine = CoreRiskRuleEngine(config=_make_config(max_drawdown_pct=0.10))
        result = engine.evaluate(
            order=_make_order(),
            current_position=None,
            account_equity_usd=85_000.0,  # 15% drawdown from 100k peak
            current_total_exposure_usd=0.0,
            peak_equity_usd=100_000.0,
        )
        assert result.allowed is False
        assert "max_drawdown" in result.blocked_by

    def test_skips_when_no_peak_equity(self) -> None:
        engine = CoreRiskRuleEngine(config=_make_config(max_drawdown_pct=0.10))
        result = engine.evaluate(
            order=_make_order(),
            current_position=None,
            account_equity_usd=10_000.0,
            current_total_exposure_usd=0.0,
            peak_equity_usd=0.0,  # No peak data
        )
        assert result.allowed is True
        check = _find_check(result.checks, "max_drawdown")
        assert check is None

    def test_skips_when_disabled(self) -> None:
        engine = CoreRiskRuleEngine(config=_make_config(max_drawdown_pct=0.0))
        result = engine.evaluate(
            order=_make_order(),
            current_position=None,
            account_equity_usd=10_000.0,
            current_total_exposure_usd=0.0,
            peak_equity_usd=100_000.0,
        )
        assert result.allowed is True
        check = _find_check(result.checks, "max_drawdown")
        assert check is None


class TestConfigValidation:
    def test_rejects_negative_daily_loss(self) -> None:
        with pytest.raises(CoreRiskRuleError, match="max_daily_loss_usd must be positive"):
            CoreRiskRuleEngine(config=_make_config(max_daily_loss_usd=-1.0))

    def test_rejects_negative_drawdown(self) -> None:
        with pytest.raises(CoreRiskRuleError, match="max_drawdown_pct must be positive"):
            CoreRiskRuleEngine(config=_make_config(max_drawdown_pct=-0.05))

    def test_zero_values_are_valid_disabled(self) -> None:
        engine = CoreRiskRuleEngine(config=_make_config(max_daily_loss_usd=0.0, max_drawdown_pct=0.0))
        assert engine is not None


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_in_memory_allows_within_limit(self) -> None:
        from services.api.rate_limiter import InMemoryRateLimiter

        limiter = InMemoryRateLimiter(window_seconds=60, max_requests=5)
        for _ in range(5):
            allowed, meta = await limiter.is_allowed("test-ip")
            assert allowed is True

    @pytest.mark.asyncio
    async def test_in_memory_blocks_over_limit(self) -> None:
        from services.api.rate_limiter import InMemoryRateLimiter

        limiter = InMemoryRateLimiter(window_seconds=60, max_requests=3)
        for _ in range(3):
            allowed, _ = await limiter.is_allowed("test-ip2")
            assert allowed is True
        allowed, meta = await limiter.is_allowed("test-ip2")
        assert allowed is False
        assert meta.get("reason") == "rate_limit"

    @pytest.mark.asyncio
    async def test_redis_falls_back_when_unavailable(self) -> None:
        from services.api.rate_limiter import RedisRateLimiter

        limiter = RedisRateLimiter(
            redis_url="redis://localhost:19999/0",  # unreachable port
            window_seconds=60,
            max_requests=5,
        )
        allowed, _ = await limiter.is_allowed("fallback-test")
        assert allowed is True


def _find_check(checks: tuple[CoreRiskCheck, ...], name: str) -> CoreRiskCheck | None:
    for c in checks:
        if c.name == name:
            return c
    return None
