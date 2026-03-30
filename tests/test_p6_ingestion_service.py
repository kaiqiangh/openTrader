from __future__ import annotations

from services.news_ingestion.ingestion_service import InMemoryNewsItemStore, NewsIngestionService
from services.news_ingestion.source_connectors import NewsSourceRecord


def _record(
    *, source: str, source_item_id: str, title: str, content: str, url: str
) -> NewsSourceRecord:
    return NewsSourceRecord(
        source=source,
        source_item_id=source_item_id,
        published_at="2026-02-14T18:00:00Z",
        title=title,
        url=url,
        content=content,
    )


def test_news_ingestion_service_dedupes_by_source_item_and_hash() -> None:
    store = InMemoryNewsItemStore()
    service = NewsIngestionService(store=store)

    records = (
        _record(
            source="rss-main",
            source_item_id="item-1",
            title="BTC ETF approval",
            content="Bitcoin ETF approval boosts crypto market optimism.",
            url="https://news/a",
        ),
        _record(
            source="rss-main",
            source_item_id="item-1",
            title="BTC ETF approval duplicate id",
            content="Different payload but same source item id.",
            url="https://news/b",
        ),
        _record(
            source="api-main",
            source_item_id="item-77",
            title="BTC ETF approval",
            content="Bitcoin ETF approval boosts crypto market optimism.",
            url="https://news/c",
        ),
        _record(
            source="api-main",
            source_item_id="item-78",
            title="ETH staking update",
            content="Ethereum staking yields remain stable.",
            url="https://news/d",
        ),
    )

    result = service.ingest(records)

    assert result.total_records == 4
    assert result.inserted_count == 2
    assert result.duplicate_count == 2
    assert {outcome.dedupe_reason for outcome in result.outcomes if not outcome.inserted} == {
        "duplicate_source_item",
        "duplicate_hash",
    }
    assert len(store.list_items()) == 2


def test_news_ingestion_service_populates_hash_and_raw_payload_fields() -> None:
    store = InMemoryNewsItemStore()
    service = NewsIngestionService(store=store)

    result = service.ingest(
        (
            _record(
                source="social-main",
                source_item_id="tw-1",
                title="Exchange reserves increase",
                content="Reserves are up this week.",
                url="https://news/x",
            ),
        )
    )

    inserted = [item for item in result.outcomes if item.inserted][0].item
    assert inserted is not None
    assert inserted.content_hash
    assert inserted.raw_payload["source"] == "social-main"
    assert inserted.raw_payload["source_item_id"] == "tw-1"
