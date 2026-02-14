from __future__ import annotations

from services.news_ingestion.ingestion_service import NormalizedNewsItem
from services.news_ingestion.tagging_relevance import NewsTag
from services.news_summarizer.summarizer_service import InMemoryNewsSummaryStore, RollingNewsSummarizer


def _item(*, news_id: str, title: str, body: str) -> NormalizedNewsItem:
    return NormalizedNewsItem(
        news_id=news_id,
        source="rss-main",
        source_item_id=f"src-{news_id}",
        url=f"https://news/{news_id}",
        title=title,
        body=body,
        published_at="2026-02-14T18:20:00Z",
        ingested_at="2026-02-14T18:21:00Z",
        content_hash=f"hash-{news_id}",
        language="en",
        raw_payload={"news_id": news_id},
    )


def _tag(*, news_id: str, symbol: str | None, topic: str, relevance: float, sentiment: float) -> NewsTag:
    return NewsTag(
        news_id=news_id,
        symbol=symbol,
        topic=topic,
        relevance_score=relevance,
        sentiment_score=sentiment,
    )


def test_news_summarizer_builds_windowed_scope_summary() -> None:
    store = InMemoryNewsSummaryStore()
    service = RollingNewsSummarizer(store=store)

    items = (
        _item(news_id="n1", title="BTC ETF inflow", body="Demand keeps rising"),
        _item(news_id="n2", title="BTC volatility cools", body="Risk is stabilizing"),
        _item(news_id="n3", title="ETH merge discussion", body="Developers coordinate"),
    )
    tags = (
        _tag(news_id="n1", symbol="BTC", topic="etf", relevance=0.95, sentiment=0.7),
        _tag(news_id="n2", symbol="BTC", topic="market", relevance=0.7, sentiment=0.2),
        _tag(news_id="n3", symbol="ETH", topic="protocol", relevance=0.8, sentiment=0.1),
    )

    summary = service.summarize_window(
        symbol_scope="BTC",
        window_start="2026-02-14T18:00:00Z",
        window_end="2026-02-14T19:00:00Z",
        items=items,
        tags=tags,
    )

    assert summary.symbol_scope == "BTC"
    assert "BTC" in summary.summary_text
    assert "BTC ETF inflow" in summary.summary_text
    assert summary.token_count > 0
    assert len(store.list_summaries()) == 1


def test_news_summarizer_returns_fallback_when_no_items_match_scope() -> None:
    store = InMemoryNewsSummaryStore()
    service = RollingNewsSummarizer(store=store)

    summary = service.summarize_window(
        symbol_scope="SOL",
        window_start="2026-02-14T18:00:00Z",
        window_end="2026-02-14T19:00:00Z",
        items=(),
        tags=(),
    )

    assert summary.summary_text == "news_unavailable"
    assert summary.token_count == 1
