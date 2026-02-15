from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
import os

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/internal", tags=["internal"])


class ExecutionDispatchCommand(BaseModel):
    command_id: str = Field(min_length=1)
    operation: Literal["CREATE_ORDER", "CANCEL_ORDER"]
    action: Literal["BUY", "SELL", "CLOSE", "CANCEL"]
    symbol: str = Field(min_length=1)
    quantity: float = Field(default=0.0)
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
    order_id = (
        (command.exchange_order_id or "").strip()
        or (command.client_order_id or "").strip()
        or f"bridge-{command.decision_id[:8]}"
    )
    status_value = "canceled" if command.operation == "CANCEL_ORDER" else "submitted"
    return ExecutionDispatchResult(
        order_id=order_id,
        status=status_value,
        raw_response={
            "accepted": True,
            "operation": command.operation,
            "action": command.action,
            "symbol": command.symbol,
            "quantity": command.quantity,
            "trace_id": command.trace_id,
            "decision_id": command.decision_id,
            "processed_at": _utc_now_iso(),
        },
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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
