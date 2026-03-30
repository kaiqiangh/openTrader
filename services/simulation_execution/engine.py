from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
import uuid

from services.shared.contracts.message_envelope import validate_envelope


class SimulationExecutionError(ValueError):
    """Raised when a simulation intent cannot be executed safely."""


@dataclass(frozen=True, slots=True)
class SimulationExecutionResult:
    order_id: str
    status: str
    action: str
    symbol: str
    quantity: float
    fill_price: float
    fee_paid: float
    events: tuple[dict[str, Any], ...]


class SimulationExecutionEngine:
    def __init__(self, *, slippage_bps: float = 3.0, fee_bps: float = 5.0) -> None:
        self.slippage_bps = max(0.0, slippage_bps)
        self.fee_bps = max(0.0, fee_bps)

    def execute_intent(self, envelope: Mapping[str, Any]) -> SimulationExecutionResult:
        validate_envelope(envelope)

        mode = str(envelope["mode"]).upper()
        if mode != "MOCK":
            raise SimulationExecutionError("SimulationExecutionEngine accepts MOCK mode only")

        payload = envelope["payload"]
        if not isinstance(payload, Mapping):
            raise SimulationExecutionError("execution intent payload must be a mapping")

        action = str(payload.get("action", "")).upper()
        symbol = str(payload.get("symbol", "")).strip()
        quantity = abs(float(payload.get("quantity", 0.0) or 0.0))
        order_type = str(payload.get("order_type", "MARKET")).upper()
        if not symbol:
            raise SimulationExecutionError("execution intent must include symbol")
        if action not in {"BUY", "SELL", "HOLD", "CLOSE"}:
            raise SimulationExecutionError(f"unsupported action: {action}")
        if order_type not in {"MARKET", "LIMIT", "STOP_MARKET", "TAKE_PROFIT_MARKET", "OCO"}:
            raise SimulationExecutionError(f"unsupported order_type: {order_type}")

        order_id = self._order_id(envelope)
        if action == "HOLD" or quantity <= 0:
            ignored_event = self._build_event(
                base_envelope=envelope,
                event_type="oms.order.ignored",
                idempotency_suffix="ignored",
                payload={
                    "order_id": order_id,
                    "action": action,
                    "symbol": symbol,
                    "quantity": quantity,
                    "status": "IGNORED",
                },
            )
            return SimulationExecutionResult(
                order_id=order_id,
                status="IGNORED",
                action=action,
                symbol=symbol,
                quantity=quantity,
                fill_price=0.0,
                fee_paid=0.0,
                events=(ignored_event,),
            )

        reference_price = self._reference_price(payload)

        # --- STOP_MARKET / TAKE_PROFIT_MARKET trigger check ---
        if order_type in {"STOP_MARKET", "TAKE_PROFIT_MARKET"}:
            trigger_price_raw = payload.get("trigger_price")
            if trigger_price_raw is None or float(trigger_price_raw) <= 0:
                raise SimulationExecutionError(
                    "trigger_price must be positive for STOP_MARKET and TAKE_PROFIT_MARKET"
                )
            trigger_price = float(trigger_price_raw)
            triggered = self._check_trigger(
                order_type=order_type,
                action=action,
                reference_price=reference_price,
                trigger_price=trigger_price,
            )
            if not triggered:
                # Order is waiting — return SUBMITTED status
                created_event = self._build_event(
                    base_envelope=envelope,
                    event_type="oms.order.created",
                    idempotency_suffix="created",
                    payload={
                        "order_id": order_id,
                        "action": action,
                        "symbol": symbol,
                        "quantity": quantity,
                        "order_type": order_type,
                        "trigger_price": trigger_price,
                        "mode": mode,
                        "status": "SUBMITTED",
                    },
                )
                return SimulationExecutionResult(
                    order_id=order_id,
                    status="SUBMITTED",
                    action=action,
                    symbol=symbol,
                    quantity=quantity,
                    fill_price=0.0,
                    fee_paid=0.0,
                    events=(created_event,),
                )

        # --- OCO handling ---
        if order_type == "OCO":
            return self._execute_oco(
                envelope=envelope, payload=payload, order_id=order_id, mode=mode
            )

        fill_price = self._apply_slippage(reference_price=reference_price, action=action)
        notional = quantity * fill_price
        fee_paid = notional * (self.fee_bps / 10_000.0)

        created_event = self._build_event(
            base_envelope=envelope,
            event_type="oms.order.created",
            idempotency_suffix="created",
            payload={
                "order_id": order_id,
                "action": action,
                "symbol": symbol,
                "quantity": quantity,
                "order_type": order_type,
                "mode": mode,
                "status": "OPEN",
            },
        )
        filled_event = self._build_event(
            base_envelope=envelope,
            event_type="oms.order.filled",
            idempotency_suffix="filled",
            payload={
                "order_id": order_id,
                "action": action,
                "symbol": symbol,
                "quantity": quantity,
                "order_type": order_type,
                "fill_price": fill_price,
                "fee_paid": fee_paid,
                "mode": mode,
                "status": "FILLED",
            },
        )
        return SimulationExecutionResult(
            order_id=order_id,
            status="FILLED",
            action=action,
            symbol=symbol,
            quantity=quantity,
            fill_price=fill_price,
            fee_paid=fee_paid,
            events=(created_event, filled_event),
        )

    def _reference_price(self, payload: Mapping[str, Any]) -> float:
        market_context = payload.get("market_context")
        if isinstance(market_context, Mapping):
            mid = market_context.get("mid_price")
            if mid is not None:
                mid_price = float(mid)
                if mid_price > 0:
                    return mid_price

        for field in ("limit_price", "price", "reference_price"):
            value = payload.get(field)
            if value is None:
                continue
            candidate = float(value)
            if candidate > 0:
                return candidate
        raise SimulationExecutionError("unable to determine positive reference price")

    @staticmethod
    def _check_trigger(
        *, order_type: str, action: str, reference_price: float, trigger_price: float
    ) -> bool:
        """Return True if the trigger condition is already met at the current price."""
        if order_type == "STOP_MARKET":
            if action == "BUY":
                # Stop buy: triggers when price rises to or above stop
                return reference_price >= trigger_price
            else:  # SELL
                # Stop sell: triggers when price falls to or below stop
                return reference_price <= trigger_price
        elif order_type == "TAKE_PROFIT_MARKET":
            if action == "SELL":
                # Take profit sell: triggers when price rises to or above target
                return reference_price >= trigger_price
            else:  # BUY (rare)
                # Take profit buy: triggers when price falls to or below target
                return reference_price <= trigger_price
        return False

    def _execute_oco(
        self, *, envelope: Mapping[str, Any], payload: Mapping[str, Any], order_id: str, mode: str
    ) -> SimulationExecutionResult:
        """Execute an OCO (One-Cancels-Other) composite order."""
        oco_legs = payload.get("oco_legs")
        if not isinstance(oco_legs, (list, tuple)) or len(oco_legs) != 2:
            raise SimulationExecutionError("OCO order requires exactly 2 oco_legs")

        action = str(payload.get("action", "")).upper()
        symbol = str(payload.get("symbol", "")).strip()
        quantity = abs(float(payload.get("quantity", 0.0) or 0.0))
        reference_price = self._reference_price(payload)

        # Evaluate each leg to see which triggers first
        triggered_leg_index: int | None = None
        for i, leg in enumerate(oco_legs):
            if not isinstance(leg, Mapping):
                raise SimulationExecutionError(f"OCO leg {i} must be a mapping")
            leg_type = str(leg.get("order_type", "")).upper()
            if leg_type == "LIMIT":
                limit_price = leg.get("limit_price")
                if limit_price is None:
                    raise SimulationExecutionError(f"OCO LIMIT leg {i} requires limit_price")
                lp = float(limit_price)
                # BUY limit: triggers when price <= limit_price
                # SELL limit: triggers when price >= limit_price
                if action == "BUY" and reference_price <= lp:
                    triggered_leg_index = i
                    break
                elif action == "SELL" and reference_price >= lp:
                    triggered_leg_index = i
                    break
            elif leg_type in {"STOP_MARKET", "TAKE_PROFIT_MARKET"}:
                trigger_price = leg.get("trigger_price")
                if trigger_price is None:
                    raise SimulationExecutionError(f"OCO {leg_type} leg {i} requires trigger_price")
                tp = float(trigger_price)
                if self._check_trigger(
                    order_type=leg_type,
                    action=action,
                    reference_price=reference_price,
                    trigger_price=tp,
                ):
                    triggered_leg_index = i
                    break

        if triggered_leg_index is None:
            # Neither leg triggered — both are waiting
            created_event = self._build_event(
                base_envelope=envelope,
                event_type="oms.order.created",
                idempotency_suffix="created",
                payload={
                    "order_id": order_id,
                    "action": action,
                    "symbol": symbol,
                    "quantity": quantity,
                    "order_type": "OCO",
                    "mode": mode,
                    "status": "SUBMITTED",
                },
            )
            return SimulationExecutionResult(
                order_id=order_id,
                status="SUBMITTED",
                action=action,
                symbol=symbol,
                quantity=quantity,
                fill_price=0.0,
                fee_paid=0.0,
                events=(created_event,),
            )

        # One leg triggered — fill it, cancel the other
        triggered_leg = oco_legs[triggered_leg_index]
        leg_type = str(triggered_leg.get("order_type", "LIMIT")).upper()
        if leg_type == "LIMIT":
            fill_price = float(triggered_leg["limit_price"])
        else:
            fill_price = self._apply_slippage(reference_price=reference_price, action=action)

        notional = quantity * fill_price
        fee_paid = notional * (self.fee_bps / 10_000.0)

        created_event = self._build_event(
            base_envelope=envelope,
            event_type="oms.order.created",
            idempotency_suffix="created",
            payload={
                "order_id": order_id,
                "action": action,
                "symbol": symbol,
                "quantity": quantity,
                "order_type": "OCO",
                "triggered_leg": triggered_leg_index,
                "mode": mode,
                "status": "OPEN",
            },
        )
        filled_event = self._build_event(
            base_envelope=envelope,
            event_type="oms.order.filled",
            idempotency_suffix="filled",
            payload={
                "order_id": order_id,
                "action": action,
                "symbol": symbol,
                "quantity": quantity,
                "order_type": "OCO",
                "triggered_leg": triggered_leg_index,
                "fill_price": fill_price,
                "fee_paid": fee_paid,
                "mode": mode,
                "status": "FILLED",
            },
        )
        cancelled_leg_index = 1 - triggered_leg_index
        cancelled_event = self._build_event(
            base_envelope=envelope,
            event_type="oms.order.cancelled",
            idempotency_suffix="cancelled",
            payload={
                "order_id": order_id,
                "action": action,
                "symbol": symbol,
                "order_type": "OCO",
                "cancelled_leg": cancelled_leg_index,
                "reason": "oco_other_leg_filled",
                "mode": mode,
                "status": "CANCELLED",
            },
        )
        return SimulationExecutionResult(
            order_id=order_id,
            status="FILLED",
            action=action,
            symbol=symbol,
            quantity=quantity,
            fill_price=fill_price,
            fee_paid=fee_paid,
            events=(created_event, filled_event, cancelled_event),
        )

    def _apply_slippage(self, *, reference_price: float, action: str) -> float:
        slip_ratio = self.slippage_bps / 10_000.0
        if action == "BUY":
            return reference_price * (1.0 + slip_ratio)
        return reference_price * (1.0 - slip_ratio)

    @staticmethod
    def _order_id(envelope: Mapping[str, Any]) -> str:
        idempotency_key = str(envelope.get("idempotency_key", ""))
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"sim-order:{idempotency_key}"))

    @staticmethod
    def _build_event(
        *,
        base_envelope: Mapping[str, Any],
        event_type: str,
        idempotency_suffix: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        emitted_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        event = {
            "trace_id": str(base_envelope["trace_id"]),
            "decision_id": str(base_envelope["decision_id"]),
            "mode": str(base_envelope["mode"]),
            "idempotency_key": f"{base_envelope['idempotency_key']}:{idempotency_suffix}",
            "event_type": event_type,
            "emitted_at": emitted_at,
            "payload": dict(payload),
            "service": "simulation_execution",
        }
        validate_envelope(event)
        return event
