from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
import asyncio
import importlib
import os
import time
import uuid

from services.api.internal_execution import (
    InternalDispatchUpstreamError,
    InternalDispatchValidationError,
    get_spot_adapter,
)
from services.shared.contracts.message_envelope import EnvelopeValidationError, validate_envelope

_TERMINAL_STATUSES = {"filled", "canceled", "rejected", "expired"}
_FILL_EVENT_TYPES = {"oms.order.partially_filled", "oms.order.filled"}


@dataclass(frozen=True, slots=True)
class LifecycleStatusSnapshot:
    exchange: str
    symbol: str
    status: str
    exchange_order_id: str | None
    client_order_id: str | None
    filled_quantity_total: float
    average_price: float | None
    fee_total: float | None
    raw_response: dict[str, Any]


@dataclass(slots=True)
class TrackedLifecycleOrder:
    tracking_key: str
    trace_id: str
    decision_id: str
    mode: str
    idempotency_key: str
    strategy_id: str
    exchange: str
    symbol: str
    action: str
    order_type: str
    time_in_force: str | None
    limit_price: float | None
    trigger_price: float | None
    reduce_only: bool
    requested_quantity: float
    client_order_id: str | None
    exchange_order_id: str | None
    status: str = "submitted"
    reported_filled_quantity: float = 0.0
    reported_fee_total: float = 0.0
    average_price: float | None = None
    emitted_events: int = 0
    terminal_marked_at_monotonic: float | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_STATUSES


class PrivateOrderStreamConnector(Protocol):
    @property
    def supports_private_stream(self) -> bool: ...

    async def poll_updates(
        self,
        *,
        tracked_orders: tuple[TrackedLifecycleOrder, ...],
        timeout_seconds: float,
    ) -> tuple[LifecycleStatusSnapshot, ...]: ...


class OrderStatusPoller(Protocol):
    async def fetch_status(
        self, *, order: TrackedLifecycleOrder
    ) -> LifecycleStatusSnapshot | None: ...


class NoopPrivateOrderStreamConnector:
    @property
    def supports_private_stream(self) -> bool:
        return False

    async def poll_updates(
        self,
        *,
        tracked_orders: tuple[TrackedLifecycleOrder, ...],
        timeout_seconds: float,
    ) -> tuple[LifecycleStatusSnapshot, ...]:
        _ = tracked_orders, timeout_seconds
        return ()


class CCXTProPrivateOrderStreamConnector:
    """Best-effort private stream connector backed by CCXT Pro watch_orders."""

    def __init__(
        self,
        *,
        exchanges: tuple[str, ...],
        watch_timeout_seconds: float = 0.6,
    ) -> None:
        self.watch_timeout_seconds = max(0.1, float(watch_timeout_seconds))
        self._clients: dict[str, Any] = {}
        self._load_clients(exchanges=exchanges)

    @property
    def supports_private_stream(self) -> bool:
        return bool(self._clients)

    async def poll_updates(
        self,
        *,
        tracked_orders: tuple[TrackedLifecycleOrder, ...],
        timeout_seconds: float,
    ) -> tuple[LifecycleStatusSnapshot, ...]:
        if not tracked_orders or not self._clients:
            return ()

        symbol_by_exchange: dict[str, str] = {}
        for order in tracked_orders:
            if order.is_terminal:
                continue
            if order.exchange not in self._clients:
                continue
            symbol_by_exchange.setdefault(order.exchange, order.symbol)
        if not symbol_by_exchange:
            return ()

        request_timeout = self.watch_timeout_seconds
        if timeout_seconds > 0:
            request_timeout = min(request_timeout, max(0.1, float(timeout_seconds)))

        snapshots: list[LifecycleStatusSnapshot] = []
        for exchange, symbol in symbol_by_exchange.items():
            client = self._clients.get(exchange)
            if client is None:
                continue
            try:
                orders = await self._watch_orders(
                    client=client, symbol=symbol, timeout_seconds=request_timeout
                )
            except Exception:  # noqa: BLE001 - private-stream errors trigger REST fallback path
                continue
            snapshots.extend(
                _normalize_ccxt_orders(exchange=exchange, symbol=symbol, orders=orders)
            )
        return tuple(snapshots)

    async def _watch_orders(self, *, client: Any, symbol: str, timeout_seconds: float) -> Any:
        watch_orders = getattr(client, "watch_orders", None)
        if watch_orders is None:
            return ()
        try:
            return await asyncio.wait_for(watch_orders(symbol), timeout=timeout_seconds)
        except TypeError:
            return await asyncio.wait_for(watch_orders(), timeout=timeout_seconds)

    def _load_clients(self, *, exchanges: tuple[str, ...]) -> None:
        try:
            module = importlib.import_module("ccxt.pro")
        except Exception:
            return
        for exchange in exchanges:
            normalized = exchange.strip().lower()
            if not normalized:
                continue
            factory = getattr(module, normalized, None)
            if factory is None:
                continue
            credentials = _ccxt_private_stream_credentials(normalized)
            if credentials is None:
                continue
            config: dict[str, Any] = {"enableRateLimit": True}
            config.update(credentials)
            try:
                self._clients[normalized] = factory(config)
            except Exception:
                continue


class SignedRESTOrderStatusPoller:
    """REST status poller using the internal signed exchange adapters."""

    def __init__(self, *, enable_real_dispatch: bool = True) -> None:
        self.enable_real_dispatch = bool(enable_real_dispatch)
        self._adapters: dict[str, Any] = {}

    async def fetch_status(self, *, order: TrackedLifecycleOrder) -> LifecycleStatusSnapshot | None:
        adapter = self._resolve_adapter(exchange=order.exchange)
        if adapter is None:
            return None

        payload = {
            "command_id": f"status-{order.decision_id}",
            "operation": "GET_ORDER_STATUS",
            "action": "CANCEL",
            "exchange": order.exchange,
            "symbol": order.symbol,
            "quantity": 0.0,
            "order_type": order.order_type,
            "time_in_force": order.time_in_force,
            "limit_price": order.limit_price,
            "trigger_price": order.trigger_price,
            "reduce_only": order.reduce_only,
            "idempotency_key": f"{order.idempotency_key}:status",
            "client_order_id": order.client_order_id,
            "exchange_order_id": order.exchange_order_id,
            "trace_id": order.trace_id,
            "decision_id": order.decision_id,
        }
        try:
            outcome = await asyncio.to_thread(adapter.get_order_status, payload=payload)
        except (InternalDispatchValidationError, InternalDispatchUpstreamError):
            return None
        except Exception:
            return None
        return _snapshot_from_dispatch_outcome(order=order, outcome=outcome)

    def _resolve_adapter(self, *, exchange: str) -> Any | None:
        normalized = exchange.strip().lower()
        if not normalized:
            return None
        existing = self._adapters.get(normalized)
        if existing is not None:
            return existing
        try:
            adapter = get_spot_adapter(normalized, enable_real_dispatch=self.enable_real_dispatch)
        except (InternalDispatchValidationError, ValueError):
            return None
        self._adapters[normalized] = adapter
        return adapter


class ExecutionLifecycleWorker:
    """Tracks REAL orders with private-stream primary and REST fallback lifecycle updates."""

    def __init__(
        self,
        *,
        broker: Any,
        private_stream_connector: PrivateOrderStreamConnector | None = None,
        status_poller: OrderStatusPoller | None = None,
        intent_queue_name: str = "execution.intent.real.lifecycle",
        stream_stale_after_seconds: float = 15.0,
        fallback_poll_interval_seconds: float = 5.0,
        terminal_retention_seconds: float = 600.0,
        max_tracked_orders: int = 10_000,
    ) -> None:
        self.broker = broker
        self.private_stream_connector = (
            private_stream_connector or NoopPrivateOrderStreamConnector()
        )
        self.status_poller = status_poller or SignedRESTOrderStatusPoller()
        self.intent_queue_name = intent_queue_name
        self.stream_stale_after_seconds = max(0.0, float(stream_stale_after_seconds))
        self.fallback_poll_interval_seconds = max(0.0, float(fallback_poll_interval_seconds))
        self.terminal_retention_seconds = max(0.0, float(terminal_retention_seconds))
        self.max_tracked_orders = max(10, int(max_tracked_orders))
        self._tracked_orders: dict[str, TrackedLifecycleOrder] = {}
        self._last_private_update_monotonic: float | None = None
        self._last_fallback_poll_monotonic: float = 0.0
        self._intents_tracked_total = 0
        self._private_updates_total = 0
        self._rest_fallback_polls_total = 0
        self._rest_fallback_updates_total = 0
        self._last_activity: dict[str, Any] = {}

    async def run_once(self, *, timeout_seconds: float) -> bool:
        did_work = False

        intent = await self.broker.consume(
            queue_name=self.intent_queue_name, timeout_seconds=timeout_seconds
        )
        if intent is not None:
            tracked = self._track_execution_intent(intent)
            did_work = tracked is not None
            if tracked is not None:
                self._intents_tracked_total += 1
                self._last_activity = {
                    "event": "intent_tracked",
                    "trace_id": tracked.trace_id,
                    "decision_id": tracked.decision_id,
                    "mode": tracked.mode,
                    "exchange": tracked.exchange,
                    "symbol": tracked.symbol,
                    "status": tracked.status,
                    "order_type": tracked.order_type,
                    "requested_quantity": tracked.requested_quantity,
                }

        open_orders = self._open_orders()
        if open_orders:
            private_updates = await self.private_stream_connector.poll_updates(
                tracked_orders=open_orders,
                timeout_seconds=timeout_seconds,
            )
            if private_updates:
                self._last_private_update_monotonic = time.monotonic()
                self._private_updates_total += len(private_updates)
            for snapshot in private_updates:
                published = await self._apply_snapshot(snapshot=snapshot, source="private_stream")
                did_work = did_work or published

        if self._should_poll_rest_fallback():
            fallback_did_work = await self._poll_rest_fallback()
            did_work = did_work or fallback_did_work
            self._last_fallback_poll_monotonic = time.monotonic()

        self._evict_terminal_orders()
        return did_work

    def _track_execution_intent(self, envelope: Mapping[str, Any]) -> TrackedLifecycleOrder | None:
        try:
            validate_envelope(envelope)
        except EnvelopeValidationError:
            return None
        if str(envelope.get("mode", "")).upper() != "REAL":
            return None
        if str(envelope.get("event_type", "")) != "execution.intent.created":
            return None
        payload = envelope.get("payload")
        if not isinstance(payload, Mapping):
            return None

        idempotency_key = str(envelope.get("idempotency_key", "")).strip()
        exchange = str(payload.get("exchange", "binance")).strip().lower()
        symbol = str(payload.get("symbol", "")).strip().upper()
        action = str(payload.get("action", "")).strip().upper()
        quantity = abs(float(payload.get("quantity", 0.0) or 0.0))
        if (
            not idempotency_key
            or not exchange
            or not symbol
            or action not in {"BUY", "SELL", "CLOSE"}
        ):
            return None
        if quantity <= 0:
            return None

        tracking_key = idempotency_key
        existing = self._tracked_orders.get(tracking_key)
        client_order_id = _strip_or_none(payload.get("client_order_id"))
        exchange_order_id = _strip_or_none(payload.get("exchange_order_id"))
        if existing is not None:
            if client_order_id:
                existing.client_order_id = client_order_id
            if exchange_order_id:
                existing.exchange_order_id = exchange_order_id
            existing.requested_quantity = quantity
            existing.action = action
            return existing

        if len(self._tracked_orders) >= self.max_tracked_orders:
            self._evict_terminal_orders(force=True)
            if len(self._tracked_orders) >= self.max_tracked_orders:
                return None

        self._tracked_orders[tracking_key] = TrackedLifecycleOrder(
            tracking_key=tracking_key,
            trace_id=str(envelope["trace_id"]),
            decision_id=str(envelope["decision_id"]),
            mode="REAL",
            idempotency_key=idempotency_key,
            strategy_id=str(payload.get("strategy_id", "")),
            exchange=exchange,
            symbol=symbol,
            action=action,
            order_type=str(payload.get("order_type", "MARKET") or "MARKET").upper(),
            time_in_force=_strip_or_none(payload.get("time_in_force")),
            limit_price=_positive_or_none(payload.get("limit_price")),
            trigger_price=_positive_or_none(payload.get("trigger_price")),
            reduce_only=bool(payload.get("reduce_only", False)),
            requested_quantity=quantity,
            client_order_id=client_order_id,
            exchange_order_id=exchange_order_id,
        )
        return self._tracked_orders[tracking_key]

    def _open_orders(self) -> tuple[TrackedLifecycleOrder, ...]:
        return tuple(order for order in self._tracked_orders.values() if not order.is_terminal)

    def _should_poll_rest_fallback(self) -> bool:
        open_orders = self._open_orders()
        if not open_orders:
            return False

        now = time.monotonic()
        if (now - self._last_fallback_poll_monotonic) < self.fallback_poll_interval_seconds:
            return False

        if not self.private_stream_connector.supports_private_stream:
            return True
        if self._last_private_update_monotonic is None:
            return True
        return (now - self._last_private_update_monotonic) >= self.stream_stale_after_seconds

    async def _poll_rest_fallback(self) -> bool:
        self._rest_fallback_polls_total += 1
        did_work = False
        for order in self._open_orders():
            snapshot = await self.status_poller.fetch_status(order=order)
            if snapshot is None:
                continue
            published = await self._apply_snapshot(snapshot=snapshot, source="rest_fallback")
            did_work = did_work or published
            if published:
                self._rest_fallback_updates_total += 1
        return did_work

    async def _apply_snapshot(self, *, snapshot: LifecycleStatusSnapshot, source: str) -> bool:
        order = self._resolve_order(snapshot=snapshot)
        if order is None:
            return False

        if snapshot.exchange_order_id and not order.exchange_order_id:
            order.exchange_order_id = snapshot.exchange_order_id
        if snapshot.client_order_id and not order.client_order_id:
            order.client_order_id = snapshot.client_order_id

        status = _normalize_status(snapshot.status)
        total_filled = max(0.0, float(snapshot.filled_quantity_total))
        if total_filled < order.reported_filled_quantity:
            total_filled = order.reported_filled_quantity
        fill_delta = max(0.0, total_filled - order.reported_filled_quantity)

        fee_total = max(0.0, float(snapshot.fee_total or 0.0))
        if fee_total < order.reported_fee_total:
            fee_total = order.reported_fee_total
        fee_delta = max(0.0, fee_total - order.reported_fee_total)

        average_price = _positive_or_none(snapshot.average_price) or order.average_price
        status_changed = status != order.status
        if not status_changed and fill_delta <= 0.0 and fee_delta <= 0.0:
            return False

        event_type = _status_to_event_type(status)
        if event_type is None:
            return False

        if event_type in _FILL_EVENT_TYPES and fill_delta <= 0.0:
            if status == "filled":
                fill_delta = max(0.0, order.requested_quantity - order.reported_filled_quantity)
            if fill_delta <= 0.0:
                return False

        quantity = fill_delta if event_type in _FILL_EVENT_TYPES else order.requested_quantity
        if quantity <= 0.0:
            return False

        order.emitted_events += 1
        event = {
            "trace_id": order.trace_id,
            "decision_id": order.decision_id,
            "mode": order.mode,
            "idempotency_key": f"{order.idempotency_key}:{source}:{order.emitted_events}",
            "event_type": event_type,
            "emitted_at": _utc_now_iso(),
            "payload": {
                "strategy_id": order.strategy_id,
                "order_id": _resolve_order_id(order),
                "exchange_order_id": order.exchange_order_id,
                "client_order_id": order.client_order_id,
                "exchange": order.exchange,
                "symbol": order.symbol,
                "mode": order.mode,
                "action": order.action,
                "order_type": order.order_type,
                "time_in_force": order.time_in_force,
                "limit_price": order.limit_price,
                "trigger_price": order.trigger_price,
                "reduce_only": order.reduce_only,
                "quantity": quantity,
                "fill_price": average_price,
                "fee_paid": fee_delta if fee_delta > 0 else 0.0,
                "status": status.upper(),
                "source": source,
            },
            "service": "execution_lifecycle_worker",
        }
        validate_envelope(event)
        await self.broker.publish(routing_key=event_type, message=event)

        order.status = status
        order.average_price = average_price
        order.reported_filled_quantity = max(order.reported_filled_quantity, total_filled)
        order.reported_fee_total = max(order.reported_fee_total, fee_total)
        if order.is_terminal:
            order.terminal_marked_at_monotonic = time.monotonic()
        self._last_activity = {
            "event": event_type,
            "source": source,
            "trace_id": order.trace_id,
            "decision_id": order.decision_id,
            "mode": order.mode,
            "order_id": _resolve_order_id(order),
            "exchange": order.exchange,
            "symbol": order.symbol,
            "status": order.status,
            "filled_quantity_total": order.reported_filled_quantity,
            "average_price": order.average_price,
        }
        return True

    def _resolve_order(self, *, snapshot: LifecycleStatusSnapshot) -> TrackedLifecycleOrder | None:
        exchange = snapshot.exchange.strip().lower()
        if not exchange:
            return None

        if snapshot.exchange_order_id:
            exchange_order_id = snapshot.exchange_order_id.strip()
            for order in self._tracked_orders.values():
                if order.exchange != exchange:
                    continue
                if order.exchange_order_id and order.exchange_order_id == exchange_order_id:
                    return order
        if snapshot.client_order_id:
            client_order_id = snapshot.client_order_id.strip()
            for order in self._tracked_orders.values():
                if order.exchange != exchange:
                    continue
                if order.client_order_id and order.client_order_id == client_order_id:
                    return order

        symbol = snapshot.symbol.strip().upper()
        if not symbol:
            return None
        candidates = [
            order
            for order in self._tracked_orders.values()
            if order.exchange == exchange and order.symbol == symbol
        ]
        if len(candidates) == 1:
            return candidates[0]
        return None

    def _evict_terminal_orders(self, *, force: bool = False) -> None:
        if not self._tracked_orders:
            return
        now = time.monotonic()
        removable: list[str] = []
        for key, order in self._tracked_orders.items():
            if not order.is_terminal:
                continue
            marked_at = order.terminal_marked_at_monotonic
            if marked_at is None:
                removable.append(key)
                continue
            if force or (now - marked_at) >= self.terminal_retention_seconds:
                removable.append(key)
        for key in removable:
            self._tracked_orders.pop(key, None)

    def activity_snapshot(self) -> dict[str, Any]:
        terminal_total = sum(1 for order in self._tracked_orders.values() if order.is_terminal)
        payload: dict[str, Any] = {
            "tracked_orders_total": len(self._tracked_orders),
            "open_orders_total": len(self._open_orders()),
            "terminal_orders_total": terminal_total,
            "private_stream_enabled": self.private_stream_connector.supports_private_stream,
            "intents_tracked_total": self._intents_tracked_total,
            "private_updates_total": self._private_updates_total,
            "rest_fallback_polls_total": self._rest_fallback_polls_total,
            "rest_fallback_updates_total": self._rest_fallback_updates_total,
        }
        if self._last_activity:
            payload["last_activity"] = dict(self._last_activity)
        return payload


def _snapshot_from_dispatch_outcome(
    *, order: TrackedLifecycleOrder, outcome: Any
) -> LifecycleStatusSnapshot:
    raw_response = (
        outcome.raw_response if isinstance(getattr(outcome, "raw_response", None), Mapping) else {}
    )
    exchange_response = raw_response.get("exchange_response")
    if not isinstance(exchange_response, Mapping):
        exchange_response = {}
    normalized_exchange = order.exchange.strip().lower()

    status = _normalize_status(
        getattr(outcome, "status", exchange_response.get("status", "submitted"))
    )
    exchange_order_id = _strip_or_none(exchange_response.get("orderId")) or order.exchange_order_id
    client_order_id = _strip_or_none(exchange_response.get("clientOrderId")) or _strip_or_none(
        exchange_response.get("clientOid")
    )
    if client_order_id is None:
        client_order_id = order.client_order_id

    filled_quantity_total = _extract_filled_quantity_total(
        exchange=normalized_exchange, response=exchange_response
    )
    average_price = _extract_average_price(
        exchange=normalized_exchange, response=exchange_response, filled=filled_quantity_total
    )
    fee_total = _extract_fee_total(exchange=normalized_exchange, response=exchange_response)

    return LifecycleStatusSnapshot(
        exchange=normalized_exchange,
        symbol=order.symbol,
        status=status,
        exchange_order_id=exchange_order_id,
        client_order_id=client_order_id,
        filled_quantity_total=filled_quantity_total,
        average_price=average_price,
        fee_total=fee_total,
        raw_response=dict(raw_response),
    )


def _normalize_ccxt_orders(
    *, exchange: str, symbol: str, orders: Any
) -> tuple[LifecycleStatusSnapshot, ...]:
    if isinstance(orders, Mapping):
        values: list[Any] = []
        maybe_orders = orders.get("orders")
        if isinstance(maybe_orders, list):
            values = maybe_orders
        else:
            values = [orders]
    elif isinstance(orders, list):
        values = list(orders)
    else:
        values = []

    snapshots: list[LifecycleStatusSnapshot] = []
    for item in values:
        if not isinstance(item, Mapping):
            continue
        status = _normalize_status(item.get("status", "submitted"))
        filled = max(0.0, _to_float(item.get("filled"), default=0.0))
        if status == "submitted" and filled > 0.0:
            status = "partially_filled"
        average_price = _positive_or_none(item.get("average")) or _positive_or_none(
            item.get("price")
        )
        fee_total = _extract_ccxt_fee_total(item)
        snapshots.append(
            LifecycleStatusSnapshot(
                exchange=exchange,
                symbol=str(item.get("symbol", symbol) or symbol).strip().upper(),
                status=status,
                exchange_order_id=_strip_or_none(item.get("id")),
                client_order_id=_strip_or_none(item.get("clientOrderId")),
                filled_quantity_total=filled,
                average_price=average_price,
                fee_total=fee_total,
                raw_response=dict(item),
            )
        )
    return tuple(snapshots)


def _extract_ccxt_fee_total(order: Mapping[str, Any]) -> float | None:
    fee = order.get("fee")
    if isinstance(fee, Mapping):
        cost = _to_float(fee.get("cost"), default=0.0)
        if cost > 0.0:
            return cost
    fees = order.get("fees")
    if isinstance(fees, list):
        total = 0.0
        for row in fees:
            if not isinstance(row, Mapping):
                continue
            total += max(0.0, _to_float(row.get("cost"), default=0.0))
        if total > 0.0:
            return total
    return None


def _ccxt_private_stream_credentials(exchange: str) -> dict[str, str] | None:
    if exchange == "binance":
        api_key = os.getenv("BINANCE_API_KEY", "").strip()
        api_secret = os.getenv("BINANCE_API_SECRET", "").strip()
        if not api_key or not api_secret:
            return None
        return {"apiKey": api_key, "secret": api_secret}
    if exchange == "bitget":
        api_key = os.getenv("BITGET_API_KEY", "").strip()
        api_secret = os.getenv("BITGET_API_SECRET", "").strip()
        passphrase = os.getenv("BITGET_API_PASSPHRASE", "").strip()
        if not api_key or not api_secret or not passphrase:
            return None
        return {"apiKey": api_key, "secret": api_secret, "password": passphrase}
    return None


def _resolve_order_id(order: TrackedLifecycleOrder) -> str:
    if order.exchange_order_id:
        return order.exchange_order_id
    if order.client_order_id:
        return order.client_order_id
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"real-order:{order.idempotency_key}"))


def _status_to_event_type(status: str) -> str | None:
    normalized = _normalize_status(status)
    mapping = {
        "submitted": "oms.order.submitted",
        "partially_filled": "oms.order.partially_filled",
        "filled": "oms.order.filled",
        "canceled": "oms.order.canceled",
        "rejected": "oms.order.rejected",
        "expired": "oms.order.expired",
    }
    return mapping.get(normalized)


def _normalize_status(status: Any) -> str:
    normalized = str(status or "").strip().lower()
    if not normalized:
        return "submitted"
    alias = {
        "new": "submitted",
        "open": "submitted",
        "live": "submitted",
        "init": "submitted",
        "pending": "submitted",
        "partially_filled": "partially_filled",
        "partial_fill": "partially_filled",
        "partiallyfilled": "partially_filled",
        "filled": "filled",
        "closed": "filled",
        "cancelled": "canceled",
        "canceled": "canceled",
        "cancel": "canceled",
        "rejected": "rejected",
        "reject": "rejected",
        "expired": "expired",
    }
    return alias.get(normalized, normalized)


def _extract_filled_quantity_total(*, exchange: str, response: Mapping[str, Any]) -> float:
    if exchange == "binance":
        return max(0.0, _to_float(response.get("executedQty"), default=0.0))
    if exchange == "bitget":
        data = _bitget_status_data(response)
        return max(
            0.0,
            _first_positive_float(
                data,
                "baseVolume",
                "filledSize",
                "fillQuantity",
                "dealSize",
                "filledAmount",
            ),
        )
    return max(0.0, _first_positive_float(response, "filled", "filledQty", "executedQty"))


def _extract_average_price(
    *, exchange: str, response: Mapping[str, Any], filled: float
) -> float | None:
    if exchange == "binance":
        cumulative_quote = _to_float(response.get("cummulativeQuoteQty"), default=0.0)
        if filled > 0 and cumulative_quote > 0:
            return cumulative_quote / filled
        return _positive_or_none(response.get("price")) or _positive_or_none(
            response.get("avgPrice")
        )
    if exchange == "bitget":
        data = _bitget_status_data(response)
        return _first_positive_or_none(data, "priceAvg", "avgPrice", "dealAvgPrice", "price")
    return _first_positive_or_none(response, "avgPrice", "average", "price")


def _extract_fee_total(*, exchange: str, response: Mapping[str, Any]) -> float | None:
    if exchange == "binance":
        fills = response.get("fills")
        if isinstance(fills, list):
            total = 0.0
            for fill in fills:
                if not isinstance(fill, Mapping):
                    continue
                total += max(0.0, _to_float(fill.get("commission"), default=0.0))
            if total > 0.0:
                return total
        return None
    if exchange == "bitget":
        data = _bitget_status_data(response)
        fee = _first_positive_float(data, "fee", "totalFee")
        return fee if fee > 0 else None
    fee_generic = _first_positive_float(response, "fee", "feePaid", "totalFee")
    return fee_generic if fee_generic > 0 else None


def _bitget_status_data(response: Mapping[str, Any]) -> Mapping[str, Any]:
    data = response.get("data")
    if isinstance(data, Mapping):
        return data
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, Mapping):
            return first
    return response


def _first_positive_or_none(data: Mapping[str, Any], *keys: str) -> float | None:
    value = _first_positive_float(data, *keys)
    if value <= 0:
        return None
    return value


def _first_positive_float(data: Mapping[str, Any], *keys: str) -> float:
    for key in keys:
        if key not in data:
            continue
        value = _to_float(data.get(key), default=0.0)
        if value > 0:
            return value
    return 0.0


def _strip_or_none(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    if not rendered:
        return None
    return rendered


def _positive_or_none(value: Any) -> float | None:
    if value is None:
        return None
    number = _to_float(value, default=0.0)
    if number <= 0:
        return None
    return number


def _to_float(value: Any, *, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
