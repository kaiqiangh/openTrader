from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from services.oms.position_engine import PositionState

_EPSILON: Final[Decimal] = Decimal("1e-9")
_ZERO: Final[Decimal] = Decimal("0")


@dataclass(frozen=True, slots=True)
class ProposedOrder:
    mode: str
    symbol: str
    side: str
    quantity: float
    price: float


@dataclass(frozen=True, slots=True)
class CoreRiskConfig:
    max_position_abs: float
    max_symbol_notional_usd: float
    max_leverage: float


@dataclass(frozen=True, slots=True)
class CoreRiskCheck:
    name: str
    passed: bool
    value: float
    limit: float
    message: str
    severity: str = "CRITICAL"


@dataclass(frozen=True, slots=True)
class CoreRiskEvaluation:
    allowed: bool
    blocked_by: tuple[str, ...]
    projected_position_qty: float
    projected_symbol_notional_usd: float
    projected_total_exposure_usd: float
    projected_leverage: float
    checks: tuple[CoreRiskCheck, ...]


class CoreRiskRuleError(ValueError):
    """Raised when risk-rule inputs are invalid."""


class CoreRiskRuleEngine:
    """Evaluates position, exposure, and leverage checks for proposed orders."""

    def __init__(self, *, config: CoreRiskConfig) -> None:
        self._config = _validate_config(config)

    def evaluate(
        self,
        *,
        order: ProposedOrder,
        current_position: PositionState | None,
        account_equity_usd: float,
        current_total_exposure_usd: float,
    ) -> CoreRiskEvaluation:
        normalized_order = _validate_order(order)
        _validate_position(order=normalized_order, position=current_position)

        signed_quantity = _signed_quantity(
            side=normalized_order.side,
            quantity=normalized_order.quantity,
        )
        current_quantity = Decimal(str(current_position.quantity)) if current_position is not None else _ZERO
        projected_quantity = current_quantity + signed_quantity

        order_price = Decimal(str(normalized_order.price))
        current_symbol_notional = abs(current_quantity) * order_price
        projected_symbol_notional = abs(projected_quantity) * order_price

        base_total_exposure = max(_ZERO, Decimal(str(current_total_exposure_usd)))
        projected_total_exposure = max(
            _ZERO,
            base_total_exposure - current_symbol_notional + projected_symbol_notional,
        )

        equity = Decimal(str(account_equity_usd))
        if equity <= _EPSILON:
            projected_leverage = Decimal("Infinity") if projected_total_exposure > _EPSILON else _ZERO
        else:
            projected_leverage = projected_total_exposure / equity

        checks = (
            CoreRiskCheck(
                name="position_limit",
                passed=abs(projected_quantity) <= self._config.max_position_abs,
                value=abs(projected_quantity),
                limit=self._config.max_position_abs,
                message="Projected absolute position must stay within limit",
            ),
            CoreRiskCheck(
                name="symbol_notional_limit",
                passed=projected_symbol_notional <= self._config.max_symbol_notional_usd,
                value=projected_symbol_notional,
                limit=self._config.max_symbol_notional_usd,
                message="Projected per-symbol notional must stay within limit",
            ),
            CoreRiskCheck(
                name="leverage_limit",
                passed=projected_leverage <= self._config.max_leverage,
                value=projected_leverage,
                limit=self._config.max_leverage,
                message="Projected account leverage must stay within limit",
            ),
        )

        blocked_by = tuple(check.name for check in checks if not check.passed)
        return CoreRiskEvaluation(
            allowed=not blocked_by,
            blocked_by=blocked_by,
            projected_position_qty=projected_quantity,
            projected_symbol_notional_usd=projected_symbol_notional,
            projected_total_exposure_usd=projected_total_exposure,
            projected_leverage=projected_leverage,
            checks=checks,
        )


def _validate_config(config: CoreRiskConfig) -> CoreRiskConfig:
    if Decimal(str(config.max_position_abs)) <= _ZERO:
        raise CoreRiskRuleError("max_position_abs must be positive")
    if Decimal(str(config.max_symbol_notional_usd)) <= _ZERO:
        raise CoreRiskRuleError("max_symbol_notional_usd must be positive")
    if Decimal(str(config.max_leverage)) <= _ZERO:
        raise CoreRiskRuleError("max_leverage must be positive")
    return config


def _validate_order(order: ProposedOrder) -> ProposedOrder:
    mode = order.mode.strip().upper()
    symbol = order.symbol.strip().upper()
    side = order.side.strip().upper()
    quantity = abs(float(order.quantity))
    price = float(order.price)

    if not mode:
        raise CoreRiskRuleError("order.mode must be set")
    if not symbol:
        raise CoreRiskRuleError("order.symbol must be set")
    if side not in {"BUY", "SELL"}:
        raise CoreRiskRuleError(f"unsupported order side: {order.side}")
    if Decimal(str(quantity)) <= _EPSILON:
        raise CoreRiskRuleError("order.quantity must be positive")
    if Decimal(str(price)) <= _EPSILON:
        raise CoreRiskRuleError("order.price must be positive")

    return ProposedOrder(mode=mode, symbol=symbol, side=side, quantity=quantity, price=price)


def _validate_position(*, order: ProposedOrder, position: PositionState | None) -> None:
    if position is None:
        return

    if position.mode.strip().upper() != order.mode:
        raise CoreRiskRuleError(
            f"position mode mismatch: position={position.mode}, order={order.mode}"
        )

    if position.symbol.strip().upper() != order.symbol:
        raise CoreRiskRuleError(
            f"position symbol mismatch: position={position.symbol}, order={order.symbol}"
        )


def _signed_quantity(*, side: str, quantity: float) -> Decimal:
    qty = Decimal(str(quantity))
    return qty if side == "BUY" else -qty
