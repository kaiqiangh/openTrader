from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from services.oms.portfolio_snapshot import PortfolioSnapshot

_EPSILON: Final[float] = 1e-9


@dataclass(frozen=True, slots=True)
class DrawdownDailyLossConfig:
    max_drawdown_pct: float
    max_daily_loss_usd: float


@dataclass(frozen=True, slots=True)
class DrawdownDailyLossCheck:
    name: str
    passed: bool
    value: float
    limit: float
    message: str
    severity: str = "CRITICAL"


@dataclass(frozen=True, slots=True)
class DrawdownDailyLossEvaluation:
    allowed: bool
    blocked_by: tuple[str, ...]
    drawdown_pct: float
    daily_loss_usd: float
    checks: tuple[DrawdownDailyLossCheck, ...]


class DrawdownDailyLossGuardError(ValueError):
    """Raised when drawdown/daily-loss guard inputs are invalid."""


class DrawdownDailyLossGuardEngine:
    """Evaluates drawdown and daily loss guardrails from portfolio snapshots."""

    def __init__(self, *, config: DrawdownDailyLossConfig) -> None:
        self._config = _validate_config(config)

    def evaluate(
        self,
        *,
        snapshot: PortfolioSnapshot,
        peak_equity_usd: float,
        daily_pnl_usd: float | None = None,
    ) -> DrawdownDailyLossEvaluation:
        peak_equity = max(0.0, float(peak_equity_usd))
        current_equity = float(snapshot.total_balance_usd)

        if peak_equity <= _EPSILON:
            drawdown_pct = 0.0
        else:
            drawdown_pct = max(0.0, (peak_equity - current_equity) / peak_equity)

        pnl_reference = float(daily_pnl_usd) if daily_pnl_usd is not None else float(snapshot.realized_pnl_total)
        daily_loss_usd = max(0.0, -pnl_reference)

        checks = (
            DrawdownDailyLossCheck(
                name="drawdown_limit",
                passed=drawdown_pct <= self._config.max_drawdown_pct,
                value=drawdown_pct,
                limit=self._config.max_drawdown_pct,
                message="Current drawdown must stay within configured threshold",
            ),
            DrawdownDailyLossCheck(
                name="daily_loss_limit",
                passed=daily_loss_usd <= self._config.max_daily_loss_usd,
                value=daily_loss_usd,
                limit=self._config.max_daily_loss_usd,
                message="Daily realized loss must stay within configured threshold",
            ),
        )

        blocked_by = tuple(check.name for check in checks if not check.passed)
        return DrawdownDailyLossEvaluation(
            allowed=not blocked_by,
            blocked_by=blocked_by,
            drawdown_pct=drawdown_pct,
            daily_loss_usd=daily_loss_usd,
            checks=checks,
        )


def _validate_config(config: DrawdownDailyLossConfig) -> DrawdownDailyLossConfig:
    if not 0.0 <= float(config.max_drawdown_pct) <= 1.0:
        raise DrawdownDailyLossGuardError("max_drawdown_pct must be between 0 and 1")
    if float(config.max_daily_loss_usd) < 0.0:
        raise DrawdownDailyLossGuardError("max_daily_loss_usd must be non-negative")
    return config
