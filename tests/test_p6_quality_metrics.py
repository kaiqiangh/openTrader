from __future__ import annotations

from services.news_ingestion.ingestion_service import NewsIngestionBatchResult, NewsIngestionOutcome, NormalizedNewsItem
from services.news_ingestion.quality_metrics import NewsQualityMetrics
from services.news_summarizer.summarizer_service import NewsSummaryArtifact


def _item(*, news_id: str, published_at: str) -> NormalizedNewsItem:
    return NormalizedNewsItem(
        news_id=news_id,
        source="rss-main",
        source_item_id=f"src-{news_id}",
        url=f"https://news/{news_id}",
        title="headline",
        body="body",
        published_at=published_at,
        ingested_at="2026-02-14T19:10:00Z",
        content_hash=f"hash-{news_id}",
        language="en",
        raw_payload={},
    )


def test_quality_metrics_snapshot_exposes_coverage_freshness_lag_and_error_rate() -> None:
    metrics = NewsQualityMetrics()

    metrics.record_connector_cycle(sources_total=4, degraded_sources=("rss-bad", "api-bad"), now_seconds=100.0)
    metrics.record_connector_cycle(sources_total=4, degraded_sources=(), now_seconds=110.0)

    batch = NewsIngestionBatchResult(
        total_records=3,
        inserted_count=2,
        duplicate_count=1,
        outcomes=(
            NewsIngestionOutcome(source="rss-main", source_item_id="a", inserted=True, dedupe_reason=None, item=_item(news_id="n1", published_at="2026-02-14T19:00:00Z")),
            NewsIngestionOutcome(source="api-main", source_item_id="b", inserted=True, dedupe_reason=None, item=_item(news_id="n2", published_at="2026-02-14T19:05:00Z")),
            NewsIngestionOutcome(source="api-main", source_item_id="c", inserted=False, dedupe_reason="duplicate_hash", item=None),
        ),
    )
    metrics.record_ingestion_batch(batch)

    summary = NewsSummaryArtifact(
        summary_id="sum-1",
        symbol_scope="BTC",
        window_start="2026-02-14T18:00:00Z",
        window_end="2026-02-14T19:00:00Z",
        summary_text="BTC summary",
        token_count=2,
        generated_at="2026-02-14T19:01:00Z",
        source_news_ids=("n1", "n2"),
    )
    metrics.record_summary_generated(summary)
    metrics.record_alert(severity="WARNING")

    snapshot = metrics.snapshot(now_seconds=120.0)

    assert snapshot["counters"]["connector_cycles_total"] == 2
    assert snapshot["counters"]["source_fetch_attempts_total"] == 8
    assert snapshot["counters"]["source_fetch_errors_total"] == 2
    assert snapshot["counters"]["news_items_inserted_total"] == 2
    assert snapshot["counters"]["news_items_duplicates_total"] == 1
    assert snapshot["counters"]["summaries_generated_total"] == 1
    assert snapshot["counters"]["alerts_total"] == 1

    assert snapshot["quality"]["coverage_ratio"] == 0.75
    assert snapshot["quality"]["error_rate"] == 0.25
    assert snapshot["quality"]["freshness_seconds_latest"] is not None
    assert snapshot["quality"]["summarization_lag_seconds_avg"] == 60.0


def test_quality_metrics_handles_empty_state() -> None:
    metrics = NewsQualityMetrics()
    snapshot = metrics.snapshot(now_seconds=200.0)

    assert snapshot["counters"]["connector_cycles_total"] == 0
    assert snapshot["quality"]["coverage_ratio"] == 1.0
    assert snapshot["quality"]["error_rate"] == 0.0
    assert snapshot["quality"]["freshness_seconds_latest"] is None
    assert snapshot["quality"]["summarization_lag_seconds_avg"] is None
