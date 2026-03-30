from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Final

_EPSILON: Final[Decimal] = Decimal("1e-9")


@dataclass(frozen=True, slots=True)
class PositionState:
    mode: str
    symbol: str
    quantity: Decimal
    average_entry_price: Decimal
    realized_pnl: Decimal
    status: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class PositionFill:
    order_id: str
    mode: str
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    fee: Decimal = Decimal("0")
    filled_at: str | None = None


@dataclass(frozen=True, slots=True)
class PositionUpdate:
    previous: PositionState
    current: PositionState
    realized_pnl_delta: Decimal


class PositionEngineError(ValueError):
    """Raised when a fill cannot be applied to the target position safely."""


class PositionEngine:
    """Applies normalized fill events to a netted position ledger."""

    def apply_fill(self, *, position: PositionState | None, fill: PositionFill) -> PositionUpdate:
        signed_fill_quantity = _signed_quantity(fill)
        fill_quantity_abs = abs(signed_fill_quantity)

        if position is None:
            previous = _empty_position(mode=fill.mode, symbol=fill.symbol)
        else:
            previous = position

        _validate_position_compatibility(position=previous, fill=fill)

        previous_quantity = previous.quantity
        previous_average = previous.average_entry_price
        realized_delta = Decimal("0")

        if abs(previous_quantity) <= _EPSILON:
            new_quantity = signed_fill_quantity
            new_average = fill.price if abs(new_quantity) > _EPSILON else Decimal("0")
        elif _same_direction(previous_quantity, signed_fill_quantity):
            new_quantity = previous_quantity + signed_fill_quantity
            weighted_notional = (abs(previous_quantity) * previous_average) + (
                fill_quantity_abs * fill.price
            )
            new_average = weighted_notional / abs(new_quantity)
        else:
            closing_quantity = min(abs(previous_quantity), fill_quantity_abs)
            if previous_quantity > 0:
                realized_delta += (fill.price - previous_average) * closing_quantity
            else:
                realized_delta += (previous_average - fill.price) * closing_quantity

            remaining = fill_quantity_abs - closing_quantity
            direction = Decimal("1") if signed_fill_quantity > 0 else Decimal("-1")
            if remaining > _EPSILON:
                new_quantity = remaining * direction
                new_average = fill.price
            else:
                new_quantity = previous_quantity + signed_fill_quantity
                if abs(new_quantity) <= _EPSILON:
                    new_quantity = Decimal("0")
                    new_average = Decimal("0")
                else:
                    new_average = previous_average

        realized_delta -= abs(fill.fee)
        new_realized_pnl = previous.realized_pnl + realized_delta
        new_status = "OPEN" if abs(new_quantity) > _EPSILON else "CLOSED"
        updated_at = fill.filled_at or _utc_now_iso()

        current = PositionState(
            mode=fill.mode,
            symbol=fill.symbol,
            quantity=new_quantity,
            average_entry_price=new_average,
            realized_pnl=new_realized_pnl,
            status=new_status,
            updated_at=updated_at,
        )
        return PositionUpdate(previous=previous, current=current, realized_pnl_delta=realized_delta)


def _signed_quantity(fill: PositionFill) -> Decimal:
    side = fill.side.strip().upper()
    quantity = abs(fill.quantity)
    if quantity <= _EPSILON:
        raise PositionEngineError("fill.quantity must be positive")
    if side == "BUY":
        return quantity
    if side == "SELL":
        return -quantity
    raise PositionEngineError(f"unsupported fill side: {fill.side}")


def _same_direction(left: Decimal, right: Decimal) -> bool:
    return (left > 0 and right > 0) or (left < 0 and right < 0)


def _empty_position(*, mode: str, symbol: str) -> PositionState:
    return PositionState(
        mode=mode,
        symbol=symbol,
        quantity=Decimal("0"),
        average_entry_price=Decimal("0"),
        realized_pnl=Decimal("0"),
        status="CLOSED",
        updated_at=_utc_now_iso(),
    )


def _validate_position_compatibility(*, position: PositionState, fill: PositionFill) -> None:
    if position.mode != fill.mode:
        raise PositionEngineError(
            f"position mode mismatch: position={position.mode}, fill={fill.mode}"
        )
    if position.symbol != fill.symbol:
        raise PositionEngineError(
            f"position symbol mismatch: position={position.symbol}, fill={fill.symbol}"
        )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
