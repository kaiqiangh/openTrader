from __future__ import annotations

import pytest

from services.agent_orchestrator.contracts import StrategyConfig
from services.agent_orchestrator.orchestrator import AgentOrchestrator
from services.market_ingestion.canonical_pipeline import CanonicalNormalizationPipeline
from services.market_ingestion.exchange_adapter import CCXTIngestionAdapter
from services.oms.fill_reconciliation import (
    ExchangeOrderSnapshot,
    FillReconciliationEngine,
    LifecycleEvent,
    ReconciliationFill,
    ReconciliationOrder,
)
from services.oms.portfolio_snapshot import PortfolioSnapshotEngine
from services.oms.position_engine import PositionEngine, PositionFill, PositionState
from services.shared.runtime.broker import InMemoryTopicBroker
from services.workers.runtime_pipeline import (
    AgentOrchestratorRuntimeWorker,
    MarketIngestionRuntimeWorker,
    RuntimeIntegrationGate,
)


class _ScriptedRestClient:
    async def fetch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, object]:
        _ = limit
        assert symbol == "BTC/USDT"
        return {
            "nonce": 400,
            "timestamp": 1739535600000,
            "bids": [[42000.0, 5.0], [41999.0, 2.0]],
            "asks": [[42001.0, 2.0], [42002.0, 1.0]],
        }


class _ScriptedWsClient:
    async def watch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, object]:
        _ = limit
        assert symbol == "BTC/USDT"
        return {
            "U": 401,
            "u": 402,
            "timestamp": 1739535601000,
            "bids": [[42000.0, 8.0], [41999.0, 2.0]],
            "asks": [[42001.0, 1.0], [42002.0, 0.5]],
        }


def _strategy() -> StrategyConfig:
    return StrategyConfig(
        strategy_id="scalp-long-short-real",
        symbol="BTC/USDT",
        mode="REAL",
        order_size=0.1,
        planner_buy_threshold=0.2,
        planner_sell_threshold=0.2,
        risk_max_notional_usd=50_000.0,
        risk_max_position_size=1.0,
        risk_max_drawdown_pct=0.3,
        risk_min_confidence=0.2,
    )


def _validate_real_intent_contract(intent: dict[str, object]) -> None:
    payload = intent["payload"]
    assert isinstance(payload, dict)
    assert intent["mode"] == "REAL"
    assert intent["event_type"] == "execution.intent.created"
    assert isinstance(intent["idempotency_key"], str) and intent["idempotency_key"]
    assert isinstance(payload.get("symbol"), str) and payload["symbol"]
    assert payload.get("action") in {"BUY", "SELL", "CLOSE", "CANCEL"}
    assert float(payload.get("quantity", 0.0)) != 0.0


def _apply_fills_to_position(
    *,
    fills: tuple[ReconciliationFill, ...],
    side: str,
    symbol: str,
) -> PositionState:
    position: PositionState | None = None
    engine = PositionEngine()
    for fill in fills:
        update = engine.apply_fill(
            position=position,
            fill=PositionFill(
                order_id=fill.order_id,
                mode="REAL",
                symbol=symbol,
                side=side,
                quantity=fill.quantity,
                price=fill.price,
                fee=fill.fee,
            ),
        )
        position = update.current
    assert position is not None
    return position


@pytest.mark.asyncio
async def test_p9_e2e_real_flow_market_to_reconciliation_with_exchange_fallback() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")

    adapter = CCXTIngestionAdapter(
        exchange="binance",
        rest_client=_ScriptedRestClient(),
        ws_client=_ScriptedWsClient(),
    )
    market_pipeline = CanonicalNormalizationPipeline(publisher=broker)
    market_worker = MarketIngestionRuntimeWorker(
        adapter=adapter,
        pipeline=market_pipeline,
        symbol="BTC/USDT",
        mode="REAL",
        depth=20,
    )
    orchestrator_worker = AgentOrchestratorRuntimeWorker(
        broker_consumer=broker,
        orchestrator=AgentOrchestrator(publisher=broker),
    )
    gate = RuntimeIntegrationGate(
        market_worker=market_worker,
        orchestrator_worker=orchestrator_worker,
        strategy=_strategy(),
    )

    cycle = await gate.run_cycle()
    assert cycle.orchestration is not None
    assert cycle.orchestration.execution_intent is not None
    assert broker.queue_size("execution.intent.mock") == 0
    assert broker.queue_size("execution.intent.real") == 1

    intent = await broker.consume(queue_name="execution.intent.real", timeout_seconds=0.0)
    assert intent is not None
    _validate_real_intent_contract(intent)

    payload = intent["payload"]
    assert isinstance(payload, dict)
    action = str(payload["action"])
    assert action in {"BUY", "SELL"}
    symbol = str(payload["symbol"])
    requested_quantity = abs(float(payload["quantity"]))
    queue_fill_quantity = requested_quantity * 0.4
    exchange_fill_quantity = requested_quantity - queue_fill_quantity
    reference_price = float(payload["market_context"]["mid_price"])
    order_id = f"real-{intent['decision_id']}"

    reconciliation = FillReconciliationEngine().reconcile(
        order=ReconciliationOrder(
            order_id=order_id,
            symbol=symbol,
            mode="REAL",
            requested_quantity=requested_quantity,
            status="SUBMITTED",
        ),
        lifecycle_events=(
            LifecycleEvent(event_type="oms.order.created"),
            LifecycleEvent(
                event_type="oms.order.partially_filled",
                fill=ReconciliationFill(
                    fill_id=f"{intent['idempotency_key']}:queue",
                    order_id=order_id,
                    quantity=queue_fill_quantity,
                    price=reference_price * 1.0005,
                    fee=0.2,
                    source="queue",
                ),
            ),
        ),
        exchange_snapshot=ExchangeOrderSnapshot(
            status="FILLED",
            filled_quantity=requested_quantity,
            average_price=reference_price * 1.0008,
            fills=(
                ReconciliationFill(
                    fill_id=f"{intent['idempotency_key']}:exchange",
                    order_id=order_id,
                    quantity=exchange_fill_quantity,
                    price=reference_price * 1.0010,
                    fee=0.25,
                    source="exchange",
                ),
            ),
        ),
    )

    assert reconciliation.status == "FILLED"
    assert reconciliation.used_exchange_fallback is True
    assert reconciliation.filled_quantity == pytest.approx(requested_quantity)
    assert len(reconciliation.fills) == 2

    position = _apply_fills_to_position(fills=reconciliation.fills, side=action, symbol=symbol)
    expected_quantity_sign = 1 if action == "BUY" else -1
    assert position.quantity * expected_quantity_sign > 0

    snapshot = PortfolioSnapshotEngine().build_snapshot(
        mode="REAL",
        available_balance_usd=5_000.0,
        locked_balance_usd=1_000.0,
        positions=(position,),
        mark_prices={symbol: reference_price},
        realized_pnl_today=position.realized_pnl,
    )
    assert snapshot.mode == "REAL"
    assert snapshot.total_balance_usd > 0.0
