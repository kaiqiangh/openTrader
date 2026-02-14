from __future__ import annotations

from services.agent_orchestrator.contracts import StrategyConfig
from services.agent_orchestrator.market_context_agent import MarketContextAgent


def _strategy() -> StrategyConfig:
    return StrategyConfig(
        strategy_id="scalp-long-short",
        symbol="BTC/USDT",
        mode="MOCK",
        order_size=0.1,
        planner_buy_threshold=0.2,
        planner_sell_threshold=0.2,
        risk_max_notional_usd=20_000.0,
        risk_max_position_size=1.0,
        risk_max_drawdown_pct=0.2,
        risk_min_confidence=0.2,
    )


def test_market_context_enriches_microstructure_and_news_payload() -> None:
    agent = MarketContextAgent()
    result = agent.enrich(
        payload={
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "timestamp_ms": 1_739_535_602_000,
            "bids": [{"price": 42_000.0, "amount": 4.0}],
            "asks": [{"price": 42_001.0, "amount": 1.0}],
            "current_position": 0.1,
            "drawdown_pct": 0.01,
            "news": {
                "summary": "ETF inflow acceleration reported",
                "sentiment": 0.65,
                "source_count": 5,
            },
        },
        strategy=_strategy(),
    )

    assert result.context["microstructure_regime"] == "bid_dominant"
    assert result.context["spread_bps"] > 0
    assert result.context["orderbook_imbalance"] > 0
    assert result.news["summary"].startswith("ETF inflow")
    assert result.news["is_fallback"] is False
    assert result.quality["has_news"] is True


def test_market_context_falls_back_when_news_missing() -> None:
    agent = MarketContextAgent()
    result = agent.enrich(
        payload={
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "timestamp_ms": 1_739_535_602_000,
            "bids": [{"price": 42_000.0, "amount": 1.2}],
            "asks": [{"price": 42_001.0, "amount": 2.4}],
            "current_position": 0.1,
            "drawdown_pct": 0.01,
        },
        strategy=_strategy(),
    )

    assert result.news["summary"] == "news_unavailable"
    assert result.news["is_fallback"] is True
    assert result.quality["has_news"] is False
    assert "news_unavailable" in " ".join(result.notes)


def test_market_context_handles_missing_orderbook_levels() -> None:
    agent = MarketContextAgent()
    result = agent.enrich(
        payload={
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "timestamp_ms": 1_739_535_602_000,
            "mid_price": 42_000.0,
            "current_position": 0.1,
            "drawdown_pct": 0.01,
        },
        strategy=_strategy(),
    )

    assert result.context["best_bid"] is None
    assert result.context["best_ask"] is None
    assert result.context["spread_bps"] == 0.0
    assert result.context["microstructure_regime"] == "unknown"
    assert result.quality["has_orderbook"] is False
