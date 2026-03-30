from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Final

from services.oms.state_machine import TERMINAL_STATES, normalize_state

_EPSILON: Final[float] = 1e-9
_EVENT_STATUS_MAP: Final[dict[str, str]] = {
    "oms.order.created": "OPEN",
    "oms.order.submitted": "SUBMITTED",
    "oms.order.open": "OPEN",
    "oms.order.partially_filled": "PARTIALLY_FILLED",
    "oms.order.filled": "FILLED",
    "oms.order.canceled": "CANCELED",
    "oms.order.cancelled": "CANCELED",
    "oms.order.rejected": "REJECTED",
    "oms.order.expired": "EXPIRED",
    "oms.order.ignored": "CANCELED",
}
_STATUS_PRIORITY: Final[dict[str, int]] = {
    "NEW": 0,
    "SUBMITTED": 1,
    "OPEN": 2,
    "PARTIALLY_FILLED": 3,
    "EXPIRED": 4,
    "REJECTED": 5,
    "CANCELED": 6,
    "FILLED": 7,
}


@dataclass(frozen=True, slots=True)
class ReconciliationOrder:
    order_id: str
    symbol: str
    mode: str
    requested_quantity: float
    status: str = "NEW"
    filled_quantity: float = 0.0
    average_price: float | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationFill:
    fill_id: str
    order_id: str
    quantity: float
    price: float
    fee: float = 0.0
    source: str = "queue"


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    event_type: str
    status: str | None = None
    fill: ReconciliationFill | None = None


@dataclass(frozen=True, slots=True)
class ExchangeOrderSnapshot:
    status: str
    filled_quantity: float
    average_price: float | None
    fills: tuple[ReconciliationFill, ...] = ()


@dataclass(frozen=True, slots=True)
class FillReconciliationResult:
    order_id: str
    status: str
    filled_quantity: float
    average_price: float | None
    fills: tuple[ReconciliationFill, ...]
    used_exchange_fallback: bool
    changed: bool


class FillReconciliationEngine:
    """Reconciles queue lifecycle events with optional exchange snapshot fallback."""

    def reconcile(
        self,
        *,
        order: ReconciliationOrder,
        lifecycle_events: Iterable[LifecycleEvent] = (),
        exchange_snapshot: ExchangeOrderSnapshot | None = None,
    ) -> FillReconciliationResult:
        base_status = normalize_state(order.status)
        event_statuses: list[str] = []
        queue_fills: list[ReconciliationFill] = []

        for event in lifecycle_events:
            inferred_status = _event_status(event)
            if inferred_status is not None:
                event_statuses.append(inferred_status)
            if event.fill is not None and event.fill.order_id == order.order_id:
                queue_fills.append(_normalize_fill(event.fill))

        merged_fills = _dedupe_fills(queue_fills)
        merged_status = _pick_status([base_status, *event_statuses])

        used_exchange_fallback = False
        if exchange_snapshot is not None and _requires_fallback(
            current_status=merged_status,
            queue_fills=merged_fills,
            exchange_snapshot=exchange_snapshot,
        ):
            used_exchange_fallback = True
            snapshot_status = normalize_state(exchange_snapshot.status)
            merged_status = _pick_status([merged_status, snapshot_status])
            merged_fills = _dedupe_fills([*merged_fills, *(_normalize_fill(fill) for fill in exchange_snapshot.fills)])

        filled_quantity = _filled_quantity(merged_fills)
        if filled_quantity <= _EPSILON:
            filled_quantity = max(0.0, float(order.filled_quantity))
            if exchange_snapshot is not None:
                filled_quantity = max(filled_quantity, max(0.0, float(exchange_snapshot.filled_quantity)))

        average_price = _weighted_average_price(merged_fills)
        if average_price is None:
            if exchange_snapshot is not None:
                average_price = exchange_snapshot.average_price
            if average_price is None:
                average_price = order.average_price

        final_status = _derive_status(
            base_status=merged_status,
            requested_quantity=max(0.0, float(order.requested_quantity)),
            filled_quantity=filled_quantity,
        )

        changed = _is_changed(
            order=order,
            status=final_status,
            filled_quantity=filled_quantity,
            average_price=average_price,
        )

        return FillReconciliationResult(
            order_id=order.order_id,
            status=final_status,
            filled_quantity=filled_quantity,
            average_price=average_price,
            fills=tuple(merged_fills),
            used_exchange_fallback=used_exchange_fallback,
            changed=changed,
        )


def _event_status(event: LifecycleEvent) -> str | None:
    if event.status is not None:
        return normalize_state(event.status)
    mapped = _EVENT_STATUS_MAP.get(event.event_type)
    if mapped is None:
        return None
    return normalize_state(mapped)


def _pick_status(statuses: Iterable[str]) -> str:
    best = "NEW"
    best_rank = _STATUS_PRIORITY[best]
    for status in statuses:
        normalized = normalize_state(status)
        rank = _STATUS_PRIORITY[normalized]
        if rank > best_rank:
            best = normalized
            best_rank = rank
    return best


def _requires_fallback(
    *,
    current_status: str,
    queue_fills: Iterable[ReconciliationFill],
    exchange_snapshot: ExchangeOrderSnapshot,
) -> bool:
    normalized_snapshot_status = normalize_state(exchange_snapshot.status)
    queue_filled = _filled_quantity(queue_fills)
    snapshot_filled = max(0.0, float(exchange_snapshot.filled_quantity))

    # Fallback only when exchange has strictly more information:
    # 1. Exchange shows a terminal state while queue doesn't yet
    # 2. Exchange shows more fills than queue (queue missed some fills)
    if current_status not in TERMINAL_STATES:
        if normalized_snapshot_status in TERMINAL_STATES:
            return True
        if snapshot_filled > (queue_filled + _EPSILON):
            return True
        return False

    if normalized_snapshot_status in TERMINAL_STATES and _STATUS_PRIORITY[normalized_snapshot_status] > _STATUS_PRIORITY[current_status]:
        return True
    return snapshot_filled > (queue_filled + _EPSILON)


def _derive_status(*, base_status: str, requested_quantity: float, filled_quantity: float) -> str:
    normalized = normalize_state(base_status)
    if requested_quantity <= _EPSILON:
        return normalized

    if filled_quantity >= (requested_quantity - _EPSILON):
        return "FILLED"

    if filled_quantity > _EPSILON:
        if normalized in {"CANCELED", "REJECTED", "EXPIRED"}:
            return normalized
        return "PARTIALLY_FILLED"

    return normalized


def _normalize_fill(fill: ReconciliationFill) -> ReconciliationFill:
    return ReconciliationFill(
        fill_id=fill.fill_id,
        order_id=fill.order_id,
        quantity=max(0.0, abs(float(fill.quantity))),
        price=float(fill.price),
        fee=float(fill.fee),
        source=fill.source,
    )


def _dedupe_fills(fills: Iterable[ReconciliationFill]) -> list[ReconciliationFill]:
    deduped: list[ReconciliationFill] = []
    seen: set[str] = set()
    for fill in fills:
        if fill.fill_id in seen:
            continue
        seen.add(fill.fill_id)
        deduped.append(fill)
    return deduped


def _filled_quantity(fills: Iterable[ReconciliationFill]) -> float:
    return sum(max(0.0, float(fill.quantity)) for fill in fills)


def _weighted_average_price(fills: Iterable[ReconciliationFill]) -> float | None:
    total_quantity = 0.0
    notional = 0.0
    for fill in fills:
        quantity = max(0.0, float(fill.quantity))
        total_quantity += quantity
        notional += quantity * float(fill.price)
    if total_quantity <= _EPSILON:
        return None
    return notional / total_quantity


def _is_changed(
    *,
    order: ReconciliationOrder,
    status: str,
    filled_quantity: float,
    average_price: float | None,
) -> bool:
    if normalize_state(order.status) != status:
        return True
    if abs(float(order.filled_quantity) - float(filled_quantity)) > _EPSILON:
        return True

    existing_average = order.average_price
    if existing_average is None and average_price is None:
        return False
    if existing_average is None or average_price is None:
        return True
    return abs(float(existing_average) - float(average_price)) > _EPSILON
