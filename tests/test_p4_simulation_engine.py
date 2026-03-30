from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from services.shared.runtime.broker import InMemoryTopicBroker
from services.simulation_execution.engine import SimulationExecutionEngine, SimulationExecutionError
from services.simulation_execution.worker import SimulationExecutionWorker


def _intent_envelope(
    *,
    mode: str = "MOCK",
    action: str = "BUY",
    quantity: float = 0.2,
    order_type: str = "MARKET",
    trigger_price: float | None = None,
    limit_price: float | None = None,
    mid_price: float = 42000.0,
    oco_legs: list[dict] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "strategy_id": "scalp-long-short",
        "symbol": "BTC/USDT",
        "action": action,
        "quantity": quantity,
        "order_type": order_type,
        "market_context": {"mid_price": mid_price},
    }
    if trigger_price is not None:
        payload["trigger_price"] = trigger_price
    if limit_price is not None:
        payload["limit_price"] = limit_price
    if oco_legs is not None:
        payload["oco_legs"] = oco_legs
    return {
        "trace_id": str(uuid.uuid4()),
        "decision_id": str(uuid.uuid4()),
        "mode": mode,
        "idempotency_key": f"execution.intent:{mode.lower()}:{uuid.uuid4()}",
        "event_type": "execution.intent.created",
        "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "payload": payload,
    }


def test_simulation_engine_executes_buy_with_slippage_and_fee() -> None:
    engine = SimulationExecutionEngine(slippage_bps=2.0, fee_bps=5.0)

    result = engine.execute_intent(_intent_envelope(action="BUY", quantity=0.4))

    assert result.status == "FILLED"
    assert result.action == "BUY"
    assert result.quantity == 0.4
    assert result.fill_price > 42000.0
    assert result.fee_paid > 0
    assert len(result.events) == 2
    assert result.events[0]["event_type"] == "oms.order.created"
    assert result.events[1]["event_type"] == "oms.order.filled"


def test_simulation_engine_ignores_hold_action() -> None:
    engine = SimulationExecutionEngine()

    result = engine.execute_intent(_intent_envelope(action="HOLD", quantity=0.0))

    assert result.status == "IGNORED"
    assert len(result.events) == 1
    assert result.events[0]["event_type"] == "oms.order.ignored"


def test_simulation_engine_rejects_non_mock_mode() -> None:
    engine = SimulationExecutionEngine()

    with pytest.raises(SimulationExecutionError):
        engine.execute_intent(_intent_envelope(mode="REAL"))


@pytest.mark.asyncio
async def test_simulation_worker_consumes_mock_intent_and_publishes_oms_events() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    worker = SimulationExecutionWorker(broker=broker)

    await broker.publish(routing_key="execution.intent.mock", message=_intent_envelope())
    result = await worker.run_once(timeout_seconds=0.0)

    assert result is not None
    assert result.status == "FILLED"
    assert broker.queue_size("oms.events.order_updates") == 2


# ── STOP_MARKET tests ──────────────────────────────────────────────────────


def test_stop_market_buy_triggers_when_price_rises_to_trigger() -> None:
    """STOP_MARKET BUY triggers when current price >= trigger_price."""
    engine = SimulationExecutionEngine(slippage_bps=3.0, fee_bps=5.0)
    # Mid price is 43000, trigger is 42500 → already crossed
    result = engine.execute_intent(
        _intent_envelope(
            action="BUY", order_type="STOP_MARKET", trigger_price=42500.0, mid_price=43000.0
        )
    )
    assert result.status == "FILLED"
    assert result.fill_price > 0
    assert result.fee_paid > 0


def test_stop_market_sell_triggers_when_price_falls_to_trigger() -> None:
    """STOP_MARKET SELL triggers when current price <= trigger_price."""
    engine = SimulationExecutionEngine(slippage_bps=3.0, fee_bps=5.0)
    # Mid price is 41000, trigger is 41500 → already below trigger
    result = engine.execute_intent(
        _intent_envelope(
            action="SELL", order_type="STOP_MARKET", trigger_price=41500.0, mid_price=41000.0
        )
    )
    assert result.status == "FILLED"
    assert result.fill_price > 0


def test_stop_market_buy_stays_submitted_when_price_below_trigger() -> None:
    """STOP_MARKET BUY stays SUBMITTED when current price < trigger_price."""
    engine = SimulationExecutionEngine()
    # Mid price is 42000, trigger is 43000 → not yet triggered
    result = engine.execute_intent(
        _intent_envelope(
            action="BUY", order_type="STOP_MARKET", trigger_price=43000.0, mid_price=42000.0
        )
    )
    assert result.status == "SUBMITTED"
    assert result.fill_price == 0.0
    assert result.fee_paid == 0.0
    assert len(result.events) == 1
    assert result.events[0]["event_type"] == "oms.order.created"
    assert result.events[0]["payload"]["status"] == "SUBMITTED"


def test_stop_market_sell_stays_submitted_when_price_above_trigger() -> None:
    """STOP_MARKET SELL stays SUBMITTED when current price > trigger_price."""
    engine = SimulationExecutionEngine()
    # Mid price is 42000, trigger is 41000 → not yet triggered
    result = engine.execute_intent(
        _intent_envelope(
            action="SELL", order_type="STOP_MARKET", trigger_price=41000.0, mid_price=42000.0
        )
    )
    assert result.status == "SUBMITTED"
    assert result.fill_price == 0.0


# ── TAKE_PROFIT_MARKET tests ───────────────────────────────────────────────


def test_take_profit_market_sell_triggers_when_price_rises() -> None:
    """TAKE_PROFIT_MARKET SELL triggers when current price >= trigger_price."""
    engine = SimulationExecutionEngine(slippage_bps=3.0, fee_bps=5.0)
    # Mid price is 44000, trigger is 43500 → already above target
    result = engine.execute_intent(
        _intent_envelope(
            action="SELL", order_type="TAKE_PROFIT_MARKET", trigger_price=43500.0, mid_price=44000.0
        )
    )
    assert result.status == "FILLED"
    assert result.fill_price > 0


def test_take_profit_market_sell_stays_submitted_when_below_target() -> None:
    """TAKE_PROFIT_MARKET SELL stays SUBMITTED when price hasn't reached target."""
    engine = SimulationExecutionEngine()
    # Mid price is 42000, trigger is 44000 → not yet triggered
    result = engine.execute_intent(
        _intent_envelope(
            action="SELL", order_type="TAKE_PROFIT_MARKET", trigger_price=44000.0, mid_price=42000.0
        )
    )
    assert result.status == "SUBMITTED"
    assert result.fill_price == 0.0


def test_take_profit_market_buy_triggers_when_price_falls() -> None:
    """TAKE_PROFIT_MARKET BUY triggers when current price <= trigger_price."""
    engine = SimulationExecutionEngine(slippage_bps=3.0, fee_bps=5.0)
    # Mid price is 40000, trigger is 41000 → already below target
    result = engine.execute_intent(
        _intent_envelope(
            action="BUY", order_type="TAKE_PROFIT_MARKET", trigger_price=41000.0, mid_price=40000.0
        )
    )
    assert result.status == "FILLED"


# ── STOP_MARKET trigger_price validation ────────────────────────────────────


def test_stop_market_rejects_missing_trigger_price() -> None:
    engine = SimulationExecutionEngine()
    with pytest.raises(SimulationExecutionError, match="trigger_price must be positive"):
        engine.execute_intent(
            _intent_envelope(action="BUY", order_type="STOP_MARKET", mid_price=42000.0)
        )


def test_stop_market_rejects_zero_trigger_price() -> None:
    engine = SimulationExecutionEngine()
    with pytest.raises(SimulationExecutionError, match="trigger_price must be positive"):
        engine.execute_intent(
            _intent_envelope(
                action="BUY", order_type="STOP_MARKET", trigger_price=0.0, mid_price=42000.0
            )
        )


# ── OCO tests ──────────────────────────────────────────────────────────────


def test_oco_fills_limit_leg_when_limit_price_reached() -> None:
    """OCO with SELL: if current price >= limit_price, limit leg fills."""
    engine = SimulationExecutionEngine(slippage_bps=3.0, fee_bps=5.0)
    # Current price 44000, limit sell at 43500 (already reached), stop at 41000 (not triggered)
    oco_legs = [
        {"order_type": "LIMIT", "limit_price": 43500.0},
        {"order_type": "STOP_MARKET", "trigger_price": 41000.0},
    ]
    result = engine.execute_intent(
        _intent_envelope(
            action="SELL", order_type="OCO", oco_legs=oco_legs, mid_price=44000.0, quantity=0.5
        )
    )
    assert result.status == "FILLED"
    assert result.fill_price == 43500.0  # fills at limit price
    assert len(result.events) == 3
    event_types = [e["event_type"] for e in result.events]
    assert "oms.order.created" in event_types
    assert "oms.order.filled" in event_types
    assert "oms.order.cancelled" in event_types
    # Check cancelled event references the other leg
    cancelled = [e for e in result.events if e["event_type"] == "oms.order.cancelled"][0]
    assert cancelled["payload"]["reason"] == "oco_other_leg_filled"


def test_oco_fills_stop_leg_when_stop_triggered() -> None:
    """OCO with SELL: if current price <= stop trigger, stop leg fills."""
    engine = SimulationExecutionEngine(slippage_bps=3.0, fee_bps=5.0)
    # Current price 40500, limit sell at 44000 (not reached), stop at 41000 (triggered)
    oco_legs = [
        {"order_type": "LIMIT", "limit_price": 44000.0},
        {"order_type": "STOP_MARKET", "trigger_price": 41000.0},
    ]
    result = engine.execute_intent(
        _intent_envelope(
            action="SELL", order_type="OCO", oco_legs=oco_legs, mid_price=40500.0, quantity=0.5
        )
    )
    assert result.status == "FILLED"
    assert result.fill_price > 0  # filled with slippage
    assert len(result.events) == 3


def test_oco_stays_submitted_when_neither_leg_triggered() -> None:
    """OCO: when price is between limit and stop, neither triggers."""
    engine = SimulationExecutionEngine()
    # Current price 42000, limit sell at 44000 (not reached), stop at 40000 (not triggered)
    oco_legs = [
        {"order_type": "LIMIT", "limit_price": 44000.0},
        {"order_type": "STOP_MARKET", "trigger_price": 40000.0},
    ]
    result = engine.execute_intent(
        _intent_envelope(
            action="SELL", order_type="OCO", oco_legs=oco_legs, mid_price=42000.0, quantity=0.5
        )
    )
    assert result.status == "SUBMITTED"
    assert result.fill_price == 0.0
    assert len(result.events) == 1
    assert result.events[0]["event_type"] == "oms.order.created"


def test_oco_rejects_wrong_number_of_legs() -> None:
    engine = SimulationExecutionEngine()
    with pytest.raises(SimulationExecutionError, match="exactly 2 oco_legs"):
        engine.execute_intent(
            _intent_envelope(action="SELL", order_type="OCO", oco_legs=[], mid_price=42000.0)
        )


def test_oco_rejects_invalid_leg_structure() -> None:
    engine = SimulationExecutionEngine()
    with pytest.raises(SimulationExecutionError, match="must be a mapping"):
        engine.execute_intent(
            _intent_envelope(
                action="SELL", order_type="OCO", oco_legs=["bad", "bad"], mid_price=42000.0
            )
        )
