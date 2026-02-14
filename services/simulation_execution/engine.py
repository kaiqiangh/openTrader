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
        if not symbol:
            raise SimulationExecutionError("execution intent must include symbol")
        if action not in {"BUY", "SELL", "HOLD", "CLOSE"}:
            raise SimulationExecutionError(f"unsupported action: {action}")

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
