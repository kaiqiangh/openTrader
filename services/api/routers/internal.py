from __future__ import annotations

from typing import Any, Literal
import os

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from services.api.internal_execution import (
    InternalDispatchUpstreamError,
    InternalDispatchValidationError,
    get_spot_adapter,
    normalize_exchange,
    normalize_order_type,
    normalize_time_in_force,
    validate_create_order_fields,
)

router = APIRouter(prefix="/internal", tags=["internal"])


class ExecutionDispatchCommand(BaseModel):
    command_id: str = Field(min_length=1)
    operation: Literal["CREATE_ORDER", "CANCEL_ORDER", "GET_ORDER_STATUS"]
    action: Literal["BUY", "SELL", "CLOSE", "CANCEL"]
    exchange: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    quantity: float = Field(default=0.0)
    order_type: str = Field(default="MARKET", min_length=1)
    time_in_force: str | None = None
    limit_price: float | None = None
    trigger_price: float | None = None
    reduce_only: bool = False
    idempotency_key: str = Field(min_length=1)
    client_order_id: str | None = None
    exchange_order_id: str | None = None
    trace_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)


class ExecutionDispatchResult(BaseModel):
    order_id: str
    status: str
    raw_response: dict[str, Any]


@router.post(
    "/execution/dispatch",
    response_model=ExecutionDispatchResult,
    include_in_schema=False,
)
async def dispatch_execution_command(
    command: ExecutionDispatchCommand,
    request: Request,
) -> ExecutionDispatchResult:
    _validate_bridge_api_key(request)
    try:
        normalized_exchange = normalize_exchange(command.exchange)
        normalized_order_type = normalize_order_type(command.order_type)
        normalized_tif = normalize_time_in_force(command.time_in_force)

        payload = {
            "command_id": command.command_id,
            "operation": command.operation,
            "action": command.action,
            "exchange": normalized_exchange,
            "symbol": command.symbol,
            "quantity": float(command.quantity),
            "order_type": normalized_order_type,
            "time_in_force": normalized_tif,
            "limit_price": command.limit_price,
            "trigger_price": command.trigger_price,
            "reduce_only": bool(command.reduce_only),
            "idempotency_key": command.idempotency_key,
            "client_order_id": command.client_order_id,
            "exchange_order_id": command.exchange_order_id,
            "trace_id": command.trace_id,
            "decision_id": command.decision_id,
        }

        adapter = get_spot_adapter(normalized_exchange)
        if command.operation == "CREATE_ORDER":
            validate_create_order_fields(
                order_type=normalized_order_type,
                time_in_force=normalized_tif,
                quantity=float(command.quantity),
                limit_price=command.limit_price,
                trigger_price=command.trigger_price,
            )
            outcome = adapter.create_order(payload=payload)
        elif command.operation == "CANCEL_ORDER":
            exchange_order_id = (command.exchange_order_id or "").strip()
            client_order_id = (command.client_order_id or "").strip()
            if not exchange_order_id and not client_order_id:
                raise InternalDispatchValidationError(
                    "cancel operation requires exchange_order_id or client_order_id"
                )
            outcome = adapter.cancel_order(payload=payload)
        else:
            exchange_order_id = (command.exchange_order_id or "").strip()
            client_order_id = (command.client_order_id or "").strip()
            if not exchange_order_id and not client_order_id:
                raise InternalDispatchValidationError(
                    "status operation requires exchange_order_id or client_order_id"
                )
            outcome = adapter.get_order_status(payload=payload)
    except InternalDispatchValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except InternalDispatchUpstreamError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return ExecutionDispatchResult(
        order_id=outcome.order_id,
        status=outcome.status,
        raw_response=outcome.raw_response,
    )


def _validate_bridge_api_key(request: Request) -> None:
    expected_key = os.getenv("REAL_EXECUTION_BRIDGE_API_KEY", "").strip()
    if not expected_key:
        return

    auth_header = request.headers.get("Authorization", "").strip()
    expected_header = f"Bearer {expected_key}"
    if auth_header != expected_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid bridge authorization",
        )
