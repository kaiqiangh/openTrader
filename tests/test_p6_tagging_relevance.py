from __future__ import annotations

from services.news_ingestion.ingestion_service import NormalizedNewsItem
from services.news_ingestion.tagging_relevance import InMemoryNewsTagStore, NewsTaggingRelevancePipeline


def _item(*, news_id: str, title: str, body: str) -> NormalizedNewsItem:
    return NormalizedNewsItem(
        news_id=news_id,
        source="rss-main",
        source_item_id=f"src-{news_id}",
        url=f"https://news/{news_id}",
        title=title,
        body=body,
        published_at="2026-02-14T18:10:00Z",
        ingested_at="2026-02-14T18:11:00Z",
        content_hash=f"hash-{news_id}",
        language="en",
        raw_payload={"news_id": news_id},
    )


def test_tagging_pipeline_assigns_symbol_topic_relevance_sentiment() -> None:
    store = InMemoryNewsTagStore()
    pipeline = NewsTaggingRelevancePipeline(store=store)

    items = (
        _item(
            news_id="news-1",
            title="Bitcoin ETF inflow accelerates",
            body="BTC market outlook is bullish with strong demand",
        ),
        _item(
            news_id="news-2",
            title="Exchange hack triggers panic",
            body="Security breach sparks fear and bearish sentiment",
        ),
    )

    result = pipeline.tag_items(items)

    assert result.total_items == 2
    assert result.tagged_items == 2
    assert len(result.tags) == 2

    first = result.tags[0]
    second = result.tags[1]

    assert first.symbol == "BTC"
    assert first.topic == "etf"
    assert 0.0 <= first.relevance_score <= 1.0
    assert first.sentiment_score > 0.0

    assert second.topic in {"security", "exchange"}
    assert 0.0 <= second.relevance_score <= 1.0
    assert second.sentiment_score < 0.0


def test_tagging_pipeline_handles_general_news_without_symbol_matches() -> None:
    store = InMemoryNewsTagStore()
    pipeline = NewsTaggingRelevancePipeline(store=store)

    result = pipeline.tag_items(
        (
            _item(
                news_id="news-3",
                title="Macro liquidity update",
                body="Interest rates remain steady this week",
            ),
        )
    )

    tag = result.tags[0]
    assert tag.symbol is None
    assert tag.topic == "macro"
    assert -1.0 <= tag.sentiment_score <= 1.0
