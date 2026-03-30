from __future__ import annotations

import uuid

import pytest

from services.agent_orchestrator.contracts import StrategyConfig
from services.agent_orchestrator.market_context_agent import MarketContextAgent
from services.news_summarizer.context_injection_bridge import NewsContextInjectionBridge
from services.news_summarizer.summarizer_service import NewsSummaryArtifact
from services.shared.runtime.broker import InMemoryTopicBroker


def _summary(
    *, text: str = "BTC momentum remains positive", source_news_ids: tuple[str, ...] = ("n1", "n2")
) -> NewsSummaryArtifact:
    return NewsSummaryArtifact(
        summary_id=str(uuid.uuid4()),
        symbol_scope="BTC",
        window_start="2026-02-14T18:00:00Z",
        window_end="2026-02-14T19:00:00Z",
        summary_text=text,
        token_count=len(text.split()),
        generated_at="2026-02-14T19:00:05Z",
        source_news_ids=source_news_ids,
    )


def _strategy() -> StrategyConfig:
    return StrategyConfig(
        strategy_id="news-aware-strategy",
        symbol="BTC/USDT",
        mode="MOCK",
        order_size=0.1,
        planner_buy_threshold=0.2,
        planner_sell_threshold=-0.2,
        risk_max_notional_usd=20_000.0,
        risk_max_position_size=1.0,
        risk_max_drawdown_pct=0.2,
        risk_min_confidence=0.2,
    )


@pytest.mark.asyncio
async def test_context_bridge_publishes_summary_envelope_to_strategy_context_queue() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    broker.declare_queue("strategy.context.news")
    broker.bind_queue(routing_key="strategy.context.news", queue_name="strategy.context.news")

    bridge = NewsContextInjectionBridge(
        publisher=broker,
        context_routing_key="strategy.context.news",
    )

    envelope = await bridge.publish_summary_context(
        summary=_summary(),
        strategy_id="news-aware-strategy",
        mode="MOCK",
        trace_id=str(uuid.uuid4()),
        decision_id=str(uuid.uuid4()),
        sentiment=0.4,
        source_count=2,
    )

    consumed = await broker.consume(queue_name="strategy.context.news", timeout_seconds=0.0)

    assert consumed is not None
    assert consumed["event_type"] == "news.context.summary_ready"
    assert consumed["payload"]["strategy_id"] == "news-aware-strategy"
    assert consumed["payload"]["news"]["summary"].startswith("BTC momentum")
    assert consumed["payload"]["news"]["is_fallback"] is False
    assert envelope["idempotency_key"].startswith("news.context:")


def test_context_bridge_injects_news_payload_for_market_context_agent() -> None:
    bridge = NewsContextInjectionBridge(publisher=None)
    payload = {
        "exchange": "binance",
        "symbol": "BTC/USDT",
        "timestamp_ms": 1700000000000,
        "bids": [{"price": 42000.0, "amount": 2.0}],
        "asks": [{"price": 42005.0, "amount": 1.5}],
    }

    injected = bridge.inject_into_market_payload(
        market_payload=payload,
        summary=_summary(text="ETF inflows remain strong"),
        sentiment=0.6,
        source_count=5,
        is_fallback=False,
    )

    context = MarketContextAgent().enrich(payload=injected, strategy=_strategy())

    assert context.news["summary"].startswith("ETF inflows")
    assert context.news["sentiment"] == pytest.approx(0.6)
    assert context.news["source_count"] == 5
    assert context.news["is_fallback"] is False
