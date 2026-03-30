from __future__ import annotations

from decimal import Decimal

import pytest

from services.agent_orchestrator.contracts import StrategyConfig
from services.agent_orchestrator.orchestrator import AgentOrchestrator
from services.market_ingestion.canonical_pipeline import CanonicalNormalizationPipeline
from services.market_ingestion.exchange_adapter import CCXTIngestionAdapter
from services.oms.fill_reconciliation import (
    FillReconciliationEngine,
    LifecycleEvent,
    ReconciliationFill,
    ReconciliationOrder,
)
from services.oms.portfolio_snapshot import PortfolioSnapshotEngine
from services.oms.position_engine import PositionEngine, PositionFill
from services.shared.runtime.broker import InMemoryTopicBroker
from services.simulation_execution.worker import SimulationExecutionWorker
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
            "nonce": 300,
            "timestamp": 1739535600000,
            "bids": [[42000.0, 5.0], [41999.0, 2.0]],
            "asks": [[42001.0, 2.0], [42002.0, 1.0]],
        }


class _ScriptedWsClient:
    async def watch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, object]:
        _ = limit
        assert symbol == "BTC/USDT"
        return {
            "U": 301,
            "u": 302,
            "timestamp": 1739535601000,
            "bids": [[42000.0, 8.0], [41999.0, 2.0]],
            "asks": [[42001.0, 1.0], [42002.0, 0.5]],
        }


def _strategy() -> StrategyConfig:
    return StrategyConfig(
        strategy_id="scalp-long-short",
        symbol="BTC/USDT",
        mode="MOCK",
        order_size=0.1,
        planner_buy_threshold=0.2,
        planner_sell_threshold=0.2,
        risk_max_notional_usd=50_000.0,
        risk_max_position_size=1.0,
        risk_max_drawdown_pct=0.3,
        risk_min_confidence=0.2,
    )


def _to_lifecycle_event(envelope: dict[str, object]) -> LifecycleEvent:
    event_type = str(envelope["event_type"])
    payload = envelope["payload"]
    assert isinstance(payload, dict)

    if event_type not in {"oms.order.filled", "oms.order.partially_filled"}:
        return LifecycleEvent(event_type=event_type)

    fill_price = payload.get("fill_price", payload.get("price", 0.0))
    fill = ReconciliationFill(
        fill_id=str(envelope["idempotency_key"]),
        order_id=str(payload["order_id"]),
        quantity=Decimal(str(abs(float(payload.get("quantity", 0.0))))),
        price=Decimal(str(float(fill_price))),
        fee=Decimal(str(float(payload.get("fee_paid", payload.get("fee", 0.0))))),
        source="queue",
    )
    return LifecycleEvent(event_type=event_type, fill=fill)


@pytest.mark.asyncio
async def test_p9_e2e_mock_flow_market_to_portfolio_snapshot() -> None:
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
        mode="MOCK",
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
    assert cycle.orchestration.execution_intent["mode"] == "MOCK"
    assert broker.queue_size("execution.intent.mock") == 1

    simulation_worker = SimulationExecutionWorker(broker=broker)
    simulation_result = await simulation_worker.run_once(timeout_seconds=0.0)
    assert simulation_result is not None
    assert simulation_result.status == "FILLED"

    oms_events = await broker.drain("oms.events.order_updates")
    assert [event["event_type"] for event in oms_events] == [
        "oms.order.created",
        "oms.order.filled",
    ]
    filled_event = oms_events[-1]
    assert filled_event["payload"]["action"] == "BUY"

    intent = cycle.orchestration.execution_intent
    assert intent is not None
    requested_quantity = abs(float(intent["payload"]["quantity"]))
    order_id = str(filled_event["payload"]["order_id"])

    reconciliation = FillReconciliationEngine().reconcile(
        order=ReconciliationOrder(
            order_id=order_id,
            symbol="BTC/USDT",
            mode="MOCK",
            requested_quantity=Decimal(str(requested_quantity)),
            status="OPEN",
        ),
        lifecycle_events=tuple(_to_lifecycle_event(event) for event in oms_events),
    )

    assert reconciliation.status == "FILLED"
    assert reconciliation.filled_quantity == pytest.approx(Decimal(str(requested_quantity)))
    assert len(reconciliation.fills) == 1

    fill = reconciliation.fills[0]
    position_update = PositionEngine().apply_fill(
        position=None,
        fill=PositionFill(
            order_id=order_id,
            mode="MOCK",
            symbol="BTC/USDT",
            side=str(filled_event["payload"]["action"]),
            quantity=fill.quantity,
            price=fill.price,
            fee=fill.fee,
            filled_at=str(filled_event["emitted_at"]),
        ),
    )
    assert position_update.current.status == "OPEN"
    assert position_update.current.quantity > 0

    snapshot = PortfolioSnapshotEngine().build_snapshot(
        mode="MOCK",
        available_balance_usd=Decimal("10000.0"),
        locked_balance_usd=Decimal("500.0"),
        positions=(position_update.current,),
        mark_prices={"BTC/USDT": float(fill.price)},
        realized_pnl_total=position_update.current.realized_pnl,
    )
    assert snapshot.mode == "MOCK"
    assert snapshot.unrealized_pnl == pytest.approx(Decimal("0"))
    assert snapshot.total_balance_usd == pytest.approx(Decimal("10500.0"))
