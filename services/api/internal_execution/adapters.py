from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import base64
import hashlib
import hmac
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

_ALLOWED_EXCHANGES = {"binance", "bitget"}
_ALLOWED_ORDER_TYPES = {"MARKET", "LIMIT", "STOP_MARKET", "TAKE_PROFIT_MARKET"}
_ALLOWED_TIME_IN_FORCE = {"GTC", "IOC", "FOK"}
_REAL_MODE_ENV = "INTERNAL_EXECUTION_REAL_DISPATCH"


class InternalDispatchValidationError(ValueError):
    """Raised when internal execution command payload is semantically invalid."""


class InternalDispatchUpstreamError(RuntimeError):
    """Raised when upstream exchange dispatch fails."""


@dataclass(frozen=True, slots=True)
class DispatchOutcome:
    order_id: str
    status: str
    raw_response: dict[str, Any]


class SpotExecutionAdapter(Protocol):
    def create_order(self, *, payload: dict[str, Any]) -> DispatchOutcome: ...

    def cancel_order(self, *, payload: dict[str, Any]) -> DispatchOutcome: ...

    def get_order_status(self, *, payload: dict[str, Any]) -> DispatchOutcome: ...


class BinanceSpotExecutionAdapter:
    """Safe default path used when real dispatch is disabled."""

    def create_order(self, *, payload: dict[str, Any]) -> DispatchOutcome:
        return _simulated_outcome(exchange="binance", route="binance.spot.orders.create", status="submitted", payload=payload)

    def cancel_order(self, *, payload: dict[str, Any]) -> DispatchOutcome:
        return _simulated_outcome(exchange="binance", route="binance.spot.orders.cancel", status="canceled", payload=payload)

    def get_order_status(self, *, payload: dict[str, Any]) -> DispatchOutcome:
        return _simulated_outcome(
            exchange="binance",
            route="binance.spot.orders.status",
            status="submitted",
            payload=payload,
        )


class BitgetSpotExecutionAdapter:
    """Safe default path used when real dispatch is disabled."""

    def create_order(self, *, payload: dict[str, Any]) -> DispatchOutcome:
        return _simulated_outcome(exchange="bitget", route="bitget.spot.orders.create", status="submitted", payload=payload)

    def cancel_order(self, *, payload: dict[str, Any]) -> DispatchOutcome:
        return _simulated_outcome(exchange="bitget", route="bitget.spot.orders.cancel", status="canceled", payload=payload)

    def get_order_status(self, *, payload: dict[str, Any]) -> DispatchOutcome:
        return _simulated_outcome(
            exchange="bitget",
            route="bitget.spot.orders.status",
            status="submitted",
            payload=payload,
        )


class BinanceSignedSpotExecutionAdapter:
    """Signed Binance spot REST dispatch adapter."""

    def __init__(self) -> None:
        self.base_url = os.getenv("BINANCE_BASE_URL", "https://api.binance.com").rstrip("/")
        self.api_key = os.getenv("BINANCE_API_KEY", "").strip()
        self.api_secret = os.getenv("BINANCE_API_SECRET", "").strip()
        self.timeout_seconds = max(0.1, float(os.getenv("INTERNAL_EXECUTION_HTTP_TIMEOUT_SECONDS", "10.0")))
        self.recv_window_ms = max(1000, int(os.getenv("BINANCE_RECV_WINDOW_MS", "5000")))
        if not self.api_key or not self.api_secret:
            raise InternalDispatchValidationError(
                "missing Binance credentials for real dispatch; set BINANCE_API_KEY and BINANCE_API_SECRET"
            )

    def create_order(self, *, payload: dict[str, Any]) -> DispatchOutcome:
        order_type = str(payload.get("order_type", "MARKET")).upper()
        request_params = {
            "symbol": _to_exchange_symbol(str(payload.get("symbol", ""))),
            "side": _resolve_exchange_side(str(payload.get("action", "BUY"))),
            "type": _binance_order_type(order_type),
            "quantity": _decimal_string(payload.get("quantity")),
            "newOrderRespType": "RESULT",
        }
        client_order_id = _resolve_client_order_id(payload)
        if client_order_id:
            request_params["newClientOrderId"] = client_order_id
        if order_type == "LIMIT":
            request_params["timeInForce"] = str(payload.get("time_in_force", "GTC")).upper()
            request_params["price"] = _decimal_string(payload.get("limit_price"))
        if order_type in {"STOP_MARKET", "TAKE_PROFIT_MARKET"}:
            request_params["stopPrice"] = _decimal_string(payload.get("trigger_price"))

        response = self._signed_request(method="POST", path="/api/v3/order", params=request_params)
        order_id = str(response.get("orderId") or _resolve_order_id(payload))
        return DispatchOutcome(
            order_id=order_id,
            status=_normalize_exchange_status(response.get("status"), fallback="submitted"),
            raw_response={
                "exchange": "binance",
                "market": "spot",
                "route": "binance.spot.orders.create",
                "payload": payload,
                "exchange_response": response,
                "processed_at": _utc_now_iso(),
            },
        )

    def cancel_order(self, *, payload: dict[str, Any]) -> DispatchOutcome:
        request_params: dict[str, str] = {
            "symbol": _to_exchange_symbol(str(payload.get("symbol", ""))),
        }
        exchange_order_id = str(payload.get("exchange_order_id", "")).strip()
        client_order_id = str(payload.get("client_order_id", "")).strip()
        if exchange_order_id:
            request_params["orderId"] = exchange_order_id
        if client_order_id:
            request_params["origClientOrderId"] = client_order_id
        response = self._signed_request(method="DELETE", path="/api/v3/order", params=request_params)
        order_id = str(response.get("orderId") or exchange_order_id or client_order_id or _resolve_order_id(payload))
        return DispatchOutcome(
            order_id=order_id,
            status=_normalize_exchange_status(response.get("status"), fallback="canceled"),
            raw_response={
                "exchange": "binance",
                "market": "spot",
                "route": "binance.spot.orders.cancel",
                "payload": payload,
                "exchange_response": response,
                "processed_at": _utc_now_iso(),
            },
        )

    def get_order_status(self, *, payload: dict[str, Any]) -> DispatchOutcome:
        request_params: dict[str, str] = {
            "symbol": _to_exchange_symbol(str(payload.get("symbol", ""))),
        }
        exchange_order_id = str(payload.get("exchange_order_id", "")).strip()
        client_order_id = str(payload.get("client_order_id", "")).strip()
        if exchange_order_id:
            request_params["orderId"] = exchange_order_id
        if client_order_id:
            request_params["origClientOrderId"] = client_order_id
        response = self._signed_request(method="GET", path="/api/v3/order", params=request_params)
        order_id = str(response.get("orderId") or exchange_order_id or client_order_id or _resolve_order_id(payload))
        return DispatchOutcome(
            order_id=order_id,
            status=_normalize_exchange_status(response.get("status"), fallback="submitted"),
            raw_response={
                "exchange": "binance",
                "market": "spot",
                "route": "binance.spot.orders.status",
                "payload": payload,
                "exchange_response": response,
                "processed_at": _utc_now_iso(),
            },
        )

    def _signed_request(self, *, method: str, path: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        ordered: list[tuple[str, str]] = []
        for key, value in params.items():
            if value is None:
                continue
            rendered = str(value).strip()
            if not rendered:
                continue
            ordered.append((key, rendered))
        ordered.extend(
            [
                ("recvWindow", str(self.recv_window_ms)),
                ("timestamp", str(int(time.time() * 1000))),
            ]
        )
        query = urlencode(ordered)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()
        url = f"{self.base_url}{path}?{query}&signature={signature}"
        request = Request(
            url=url,
            method=method.upper(),
            headers={"X-MBX-APIKEY": self.api_key},
        )
        parsed = _request_json(request=request, timeout_seconds=self.timeout_seconds, provider="Binance")
        if not isinstance(parsed, Mapping):
            raise InternalDispatchUpstreamError("Binance response must be a JSON object")
        if parsed.get("code") is not None and parsed.get("msg"):
            code = str(parsed.get("code"))
            if code.startswith("-"):
                logger.warning("Binance upstream error code=%s msg=%s", code, parsed.get("msg"))
                raise InternalDispatchUpstreamError(f"Binance order rejected (code={code})")
        return parsed


class BitgetSignedSpotExecutionAdapter:
    """Signed Bitget spot REST dispatch adapter."""

    def __init__(self) -> None:
        self.base_url = os.getenv("BITGET_BASE_URL", "https://api.bitget.com").rstrip("/")
        self.api_key = os.getenv("BITGET_API_KEY", "").strip()
        self.api_secret = os.getenv("BITGET_API_SECRET", "").strip()
        self.passphrase = os.getenv("BITGET_API_PASSPHRASE", "").strip()
        self.timeout_seconds = max(0.1, float(os.getenv("INTERNAL_EXECUTION_HTTP_TIMEOUT_SECONDS", "10.0")))
        if not self.api_key or not self.api_secret or not self.passphrase:
            raise InternalDispatchValidationError(
                "missing Bitget credentials for real dispatch; set BITGET_API_KEY, BITGET_API_SECRET, BITGET_API_PASSPHRASE"
            )

    def create_order(self, *, payload: dict[str, Any]) -> DispatchOutcome:
        order_type = str(payload.get("order_type", "MARKET")).upper()
        exchange_symbol = _to_exchange_symbol(str(payload.get("symbol", "")))
        side = _resolve_exchange_side(str(payload.get("action", "BUY"))).lower()
        client_order_id = _resolve_client_order_id(payload)
        if order_type in {"STOP_MARKET", "TAKE_PROFIT_MARKET"}:
            body: dict[str, Any] = {
                "symbol": exchange_symbol,
                "side": side,
                "triggerPrice": _decimal_string(payload.get("trigger_price")),
                "triggerType": "mark_price",
                "orderType": "market",
                "size": _decimal_string(payload.get("quantity")),
                "planType": "amount",
            }
            if client_order_id:
                body["clientOid"] = client_order_id
            response = self._signed_request(
                method="POST",
                path="/api/v2/spot/trade/place-plan-order",
                query={},
                body=body,
            )
        else:
            body = {
                "symbol": exchange_symbol,
                "side": side,
                "orderType": "limit" if order_type == "LIMIT" else "market",
                "size": _decimal_string(payload.get("quantity")),
            }
            if client_order_id:
                body["clientOid"] = client_order_id
            if order_type == "LIMIT":
                body["price"] = _decimal_string(payload.get("limit_price"))
                body["force"] = _bitget_time_in_force(str(payload.get("time_in_force", "GTC")))
            response = self._signed_request(
                method="POST",
                path="/api/v2/spot/trade/place-order",
                query={},
                body=body,
            )

        response_data = _bitget_data_object(response)
        order_id = str(response_data.get("orderId") or _resolve_order_id(payload))
        return DispatchOutcome(
            order_id=order_id,
            status="submitted",
            raw_response={
                "exchange": "bitget",
                "market": "spot",
                "route": "bitget.spot.orders.create",
                "payload": payload,
                "exchange_response": response,
                "processed_at": _utc_now_iso(),
            },
        )

    def cancel_order(self, *, payload: dict[str, Any]) -> DispatchOutcome:
        body: dict[str, Any] = {
            "symbol": _to_exchange_symbol(str(payload.get("symbol", ""))),
        }
        exchange_order_id = str(payload.get("exchange_order_id", "")).strip()
        client_order_id = str(payload.get("client_order_id", "")).strip()
        if exchange_order_id:
            body["orderId"] = exchange_order_id
        if client_order_id:
            body["clientOid"] = client_order_id

        response = self._signed_request(
            method="POST",
            path="/api/v2/spot/trade/cancel-order",
            query={},
            body=body,
        )
        response_data = _bitget_data_object(response)
        order_id = str(response_data.get("orderId") or exchange_order_id or client_order_id or _resolve_order_id(payload))
        return DispatchOutcome(
            order_id=order_id,
            status="canceled",
            raw_response={
                "exchange": "bitget",
                "market": "spot",
                "route": "bitget.spot.orders.cancel",
                "payload": payload,
                "exchange_response": response,
                "processed_at": _utc_now_iso(),
            },
        )

    def get_order_status(self, *, payload: dict[str, Any]) -> DispatchOutcome:
        query: dict[str, str] = {
            "symbol": _to_exchange_symbol(str(payload.get("symbol", ""))),
        }
        exchange_order_id = str(payload.get("exchange_order_id", "")).strip()
        client_order_id = str(payload.get("client_order_id", "")).strip()
        if exchange_order_id:
            query["orderId"] = exchange_order_id
        if client_order_id:
            query["clientOid"] = client_order_id

        response = self._signed_request(
            method="GET",
            path="/api/v2/spot/trade/orderInfo",
            query=query,
            body=None,
        )
        data = response.get("data")
        if isinstance(data, list):
            row = data[0] if data else {}
        elif isinstance(data, Mapping):
            row = data
        else:
            row = {}
        order_id = str(row.get("orderId") or exchange_order_id or client_order_id or _resolve_order_id(payload))
        return DispatchOutcome(
            order_id=order_id,
            status=_normalize_exchange_status(row.get("status"), fallback="submitted"),
            raw_response={
                "exchange": "bitget",
                "market": "spot",
                "route": "bitget.spot.orders.status",
                "payload": payload,
                "exchange_response": response,
                "processed_at": _utc_now_iso(),
            },
        )

    def _signed_request(
        self,
        *,
        method: str,
        path: str,
        query: Mapping[str, Any],
        body: Mapping[str, Any] | None,
    ) -> Mapping[str, Any]:
        query_pairs: list[tuple[str, str]] = []
        for key, value in query.items():
            if value is None:
                continue
            rendered = str(value).strip()
            if not rendered:
                continue
            query_pairs.append((key, rendered))
        query_string = urlencode(query_pairs)
        request_path = path if not query_string else f"{path}?{query_string}"
        payload_text = ""
        if body:
            payload_text = json.dumps(body, separators=(",", ":"), ensure_ascii=True)
        timestamp = str(int(time.time() * 1000))
        prehash = f"{timestamp}{method.upper()}{request_path}{payload_text}"
        signature = base64.b64encode(
            hmac.new(self.api_secret.encode("utf-8"), prehash.encode("utf-8"), digestmod=hashlib.sha256).digest()
        ).decode("utf-8")

        url = f"{self.base_url}{request_path}"
        request = Request(
            url=url,
            method=method.upper(),
            data=payload_text.encode("utf-8") if payload_text else None,
            headers={
                "ACCESS-KEY": self.api_key,
                "ACCESS-SIGN": signature,
                "ACCESS-TIMESTAMP": timestamp,
                "ACCESS-PASSPHRASE": self.passphrase,
                "locale": "en-US",
                "Content-Type": "application/json",
            },
        )
        parsed = _request_json(request=request, timeout_seconds=self.timeout_seconds, provider="Bitget")
        if not isinstance(parsed, Mapping):
            raise InternalDispatchUpstreamError("Bitget response must be a JSON object")
        code = str(parsed.get("code", "")).strip()
        if code not in {"", "00000", "0"}:
            logger.warning("Bitget upstream error code=%s msg=%s", code, parsed.get("msg", "unknown error"))
            raise InternalDispatchUpstreamError(f"Bitget order rejected (code={code})")
        return parsed


def normalize_exchange(exchange: str) -> str:
    normalized = exchange.strip().lower()
    if normalized not in _ALLOWED_EXCHANGES:
        raise InternalDispatchValidationError(
            f"unsupported exchange: {exchange}; allowed={sorted(_ALLOWED_EXCHANGES)}"
        )
    return normalized


def normalize_order_type(order_type: str) -> str:
    normalized = order_type.strip().upper() or "MARKET"
    if normalized not in _ALLOWED_ORDER_TYPES:
        raise InternalDispatchValidationError(
            "order_type must be one of MARKET, LIMIT, STOP_MARKET, TAKE_PROFIT_MARKET"
        )
    return normalized


def normalize_time_in_force(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if normalized not in _ALLOWED_TIME_IN_FORCE:
        raise InternalDispatchValidationError("time_in_force must be one of GTC, IOC, FOK")
    return normalized


def validate_create_order_fields(
    *,
    order_type: str,
    time_in_force: str | None,
    quantity: float,
    limit_price: float | None,
    trigger_price: float | None,
) -> None:
    if quantity < 1e-9:
        raise InternalDispatchValidationError("quantity must be positive for create operation")

    if order_type == "MARKET":
        if limit_price is not None:
            raise InternalDispatchValidationError("limit_price is not allowed for MARKET orders")
        if trigger_price is not None:
            raise InternalDispatchValidationError("trigger_price is not allowed for MARKET orders")
        return

    if order_type == "LIMIT":
        if limit_price is None or float(limit_price) <= 0:
            raise InternalDispatchValidationError("limit_price must be positive for LIMIT orders")
        if trigger_price is not None:
            raise InternalDispatchValidationError("trigger_price is not allowed for LIMIT orders")
        if time_in_force is None:
            raise InternalDispatchValidationError("time_in_force is required for LIMIT orders")
        return

    if order_type in {"STOP_MARKET", "TAKE_PROFIT_MARKET"}:
        if trigger_price is None or float(trigger_price) <= 0:
            raise InternalDispatchValidationError(
                "trigger_price must be positive for STOP_MARKET and TAKE_PROFIT_MARKET"
            )
        if limit_price is not None:
            raise InternalDispatchValidationError(
                "limit_price is not allowed for STOP_MARKET and TAKE_PROFIT_MARKET"
            )
        return


def get_spot_adapter(exchange: str, *, enable_real_dispatch: bool | None = None) -> SpotExecutionAdapter:
    normalized = normalize_exchange(exchange)
    use_real_dispatch = _resolve_real_dispatch(enable_real_dispatch)
    if normalized == "binance":
        if use_real_dispatch:
            return BinanceSignedSpotExecutionAdapter()
        return BinanceSpotExecutionAdapter()
    if normalized == "bitget":
        if use_real_dispatch:
            return BitgetSignedSpotExecutionAdapter()
        return BitgetSpotExecutionAdapter()
    raise InternalDispatchValidationError(f"unsupported exchange: {exchange}")


def _resolve_real_dispatch(override: bool | None) -> bool:
    if override is not None:
        return bool(override)
    return _to_bool(os.getenv(_REAL_MODE_ENV, "false"))


def _to_bool(raw: str) -> bool:
    normalized = raw.strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _simulated_outcome(*, exchange: str, route: str, status: str, payload: dict[str, Any]) -> DispatchOutcome:
    order_id = _resolve_order_id(payload)
    return DispatchOutcome(
        order_id=order_id,
        status=status,
        raw_response={
            "exchange": exchange,
            "market": "spot",
            "accepted": True,
            "route": route,
            "payload": payload,
            "processed_at": _utc_now_iso(),
        },
    )


def _resolve_order_id(payload: dict[str, Any]) -> str:
    exchange_order_id = str(payload.get("exchange_order_id", "")).strip()
    client_order_id = str(payload.get("client_order_id", "")).strip()
    command_id = str(payload.get("command_id", "")).strip()
    decision_id = str(payload.get("decision_id", "")).strip()
    if exchange_order_id:
        return exchange_order_id
    if client_order_id:
        return client_order_id
    if command_id:
        return command_id
    return f"bridge-{decision_id[:8]}" if decision_id else "bridge-unknown"


def _resolve_client_order_id(payload: Mapping[str, Any]) -> str:
    candidate = str(payload.get("client_order_id", "")).strip()
    if candidate:
        return candidate[:32]
    command_id = str(payload.get("command_id", "")).strip()
    if command_id:
        return command_id[:32]
    idempotency_key = str(payload.get("idempotency_key", "")).strip()
    if not idempotency_key:
        return ""
    return idempotency_key.replace(":", "_")[:32]


def _to_exchange_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper().replace("/", "")
    if not normalized:
        raise InternalDispatchValidationError("symbol must be non-empty")
    return normalized


def _resolve_exchange_side(action: str) -> str:
    normalized = action.strip().upper()
    if normalized == "BUY":
        return "BUY"
    if normalized in {"SELL", "CLOSE"}:
        return "SELL"
    if normalized == "CANCEL":
        return "SELL"
    raise InternalDispatchValidationError(f"unsupported action for exchange dispatch: {action}")


def _binance_order_type(order_type: str) -> str:
    if order_type == "LIMIT":
        return "LIMIT"
    if order_type == "STOP_MARKET":
        return "STOP_LOSS"
    if order_type == "TAKE_PROFIT_MARKET":
        return "TAKE_PROFIT"
    return "MARKET"


def _bitget_time_in_force(value: str) -> str:
    normalized = value.strip().upper()
    if normalized == "IOC":
        return "ioc"
    if normalized == "FOK":
        return "fok"
    return "gtc"


def _decimal_string(value: Any) -> str:
    if value is None:
        raise InternalDispatchValidationError("numeric field is required")
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InternalDispatchValidationError(f"invalid numeric field value: {value}") from exc
    if decimal_value <= 0:
        raise InternalDispatchValidationError(f"numeric field must be positive: {value}")
    rendered = format(decimal_value, "f").rstrip("0").rstrip(".")
    return rendered or "0"


def _normalize_exchange_status(status: Any, *, fallback: str) -> str:
    normalized = str(status or "").strip().upper()
    if not normalized:
        return fallback
    mapping = {
        "NEW": "submitted",
        "LIVE": "submitted",
        "INIT": "submitted",
        "PARTIALLY_FILLED": "partially_filled",
        "PARTIAL_FILL": "partially_filled",
        "PARTIALLYFILLED": "partially_filled",
        "FILLED": "filled",
        "CANCELED": "canceled",
        "CANCELLED": "canceled",
        "REJECTED": "rejected",
        "EXPIRED": "expired",
    }
    return mapping.get(normalized, normalized.lower())


def _bitget_data_object(parsed: Mapping[str, Any]) -> Mapping[str, Any]:
    data = parsed.get("data")
    if isinstance(data, list):
        if not data:
            return {}
        item = data[0]
        return item if isinstance(item, Mapping) else {}
    if isinstance(data, Mapping):
        return data
    return {}


def _request_json(*, request: Request, timeout_seconds: float, provider: str) -> Any:
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - explicit provider URL
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8") if hasattr(exc, "read") else str(exc)
        raise InternalDispatchUpstreamError(f"{provider} HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise InternalDispatchUpstreamError(f"{provider} connection error: {exc.reason}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InternalDispatchUpstreamError(f"{provider} response is not valid JSON") from exc


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
