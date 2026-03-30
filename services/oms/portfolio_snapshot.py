from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping

from services.oms.position_engine import PositionState


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    snapshot_time: str
    mode: str
    total_balance_usd: Decimal
    available_balance_usd: Decimal
    locked_balance_usd: Decimal
    unrealized_pnl: Decimal
    realized_pnl_total: Decimal


class PortfolioSnapshotEngineError(ValueError):
    """Raised when snapshot inputs are incomplete or inconsistent."""


class PortfolioSnapshotEngine:
    """Builds mode-tagged portfolio snapshots from balances and marked positions."""

    def build_snapshot(
        self,
        *,
        mode: str,
        available_balance_usd: Decimal,
        locked_balance_usd: Decimal,
        positions: tuple[PositionState, ...],
        mark_prices: Mapping[str, float],
        realized_pnl_total: Decimal | None = None,
        snapshot_time: str | None = None,
    ) -> PortfolioSnapshot:
        """Build a portfolio snapshot from balances and marked positions.

        Args:
            realized_pnl_total: Cumulative realized PNL across all positions (not
                restricted to today's trades). Despite the parameter name, this
                receives the total realized PNL sum. When None, falls back to
                summing position-level realized PNL values.
        """
        unrealized_pnl = Decimal("0")
        realized_from_positions = Decimal("0")
        normalized_mode = mode.strip().upper()

        for position in positions:
            if position.mode.strip().upper() != normalized_mode:
                raise PortfolioSnapshotEngineError(
                    f"position mode mismatch: expected {normalized_mode}, got {position.mode}"
                )

            realized_from_positions += position.realized_pnl
            if abs(position.quantity) <= Decimal("1e-9"):
                continue

            mark_price = mark_prices.get(position.symbol)
            if mark_price is None:
                raise PortfolioSnapshotEngineError(
                    f"missing mark price for open position symbol: {position.symbol}"
                )
            unrealized_pnl += (
                Decimal(str(mark_price)) - position.average_entry_price
            ) * position.quantity

        realized_value = (
            realized_pnl_total if realized_pnl_total is not None else realized_from_positions
        )
        available = available_balance_usd
        locked = locked_balance_usd
        total = available + locked + unrealized_pnl

        return PortfolioSnapshot(
            snapshot_time=snapshot_time or _utc_now_iso(),
            mode=normalized_mode,
            total_balance_usd=total,
            available_balance_usd=available,
            locked_balance_usd=locked,
            unrealized_pnl=unrealized_pnl,
            realized_pnl_total=realized_value,
        )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
