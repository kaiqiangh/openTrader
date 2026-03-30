"""News ingestion worker runner."""

from __future__ import annotations

import time
from typing import Any

from services.news_ingestion.ingestion_service import InMemoryNewsItemStore, NewsIngestionService
from services.news_ingestion.x_provider_connector import XProviderConnector
from services.news_ingestion.source_connectors import (
    CallableSourceConnector,
    NewsSourceConnectorFramework,
    SourceConnectorRegistry,
)
from services.news_ingestion.tagging_relevance import InMemoryNewsTagStore, NewsTaggingRelevancePipeline
from services.news_summarizer.summarizer_service import InMemoryNewsSummaryStore, RollingNewsSummarizer
from services.workers import helpers as _helpers
from services.workers.helpers import (
    _default_news_rss_feeds,
    _infer_source_name,
    _utc_now_iso,
)


class NewsWorkerRunner:
    def __init__(
        self,
        *,
        item_store: Any | None = None,
        tag_store: Any | None = None,
        summary_store: Any | None = None,
        source_mode: str = "mock",
        rss_feeds: tuple[str, ...] = (),
        fetch_timeout_seconds: float = 8.0,
        x_enabled: bool = False,
        x_api_base_url: str = "https://api.x.com/2/tweets/search/recent",
        x_bearer_token: str | None = None,
        x_query: str = "bitcoin OR ethereum OR solana",
    ) -> None:
        self.item_store = item_store or InMemoryNewsItemStore()
        self.tag_store = tag_store or InMemoryNewsTagStore()
        self.summary_store = summary_store or InMemoryNewsSummaryStore()
        self.source_mode = source_mode.strip().lower() or "mock"
        self.rss_feeds = tuple(feed.strip() for feed in rss_feeds if feed.strip())
        self.fetch_timeout_seconds = max(1.0, float(fetch_timeout_seconds))
        self.x_enabled = bool(x_enabled)
        self.x_api_base_url = x_api_base_url.strip()
        self.x_bearer_token = (x_bearer_token or "").strip()
        self.x_query = x_query.strip() or "bitcoin OR ethereum OR solana"

        registry = SourceConnectorRegistry()
        if self.source_mode == "real":
            feeds = self.rss_feeds or _default_news_rss_feeds()
            for idx, feed_url in enumerate(feeds):
                connector_id = f"rss.{_infer_source_name(feed_url)}.{idx + 1}"
                registry.register(
                    CallableSourceConnector(
                        connector_id=connector_id,
                        connector_kind="rss",
                        fetcher=lambda since, limit, _feed_url=feed_url: self._fetch_rss_records(
                            feed_url=_feed_url,
                            since=since,
                            limit=limit,
                        ),
                    )
                )
            if self.x_enabled and self.x_bearer_token:
                x_connector = XProviderConnector(
                    connector_id="social.x",
                    api_base_url=self.x_api_base_url,
                    bearer_token=self.x_bearer_token,
                    query=self.x_query,
                    timeout_seconds=self.fetch_timeout_seconds,
                )
                registry.register(
                    CallableSourceConnector(
                        connector_id="social.x",
                        connector_kind="social",
                        fetcher=lambda since, limit: x_connector.fetch_records(since=since, limit=limit),
                    )
                )
        else:
            registry.register(
                CallableSourceConnector(
                    connector_id="mock.crypto",
                    connector_kind="custom",
                    fetcher=self._fetch_mock_records,
                )
            )
        self.framework = NewsSourceConnectorFramework(registry=registry)
        self.ingestion = NewsIngestionService(store=self.item_store)
        self.tagging = NewsTaggingRelevancePipeline(store=self.tag_store)
        self.summarizer = RollingNewsSummarizer(store=self.summary_store)
        self._last_activity: dict[str, Any] = {}

    async def run_once(self, *, timeout_seconds: float) -> bool:
        _ = timeout_seconds
        cycle = self.framework.fetch_cycle(limit_per_source=10)
        self._last_activity = {
            "event": "news.fetch_cycle",
            "source_mode": self.source_mode,
            "sources_total": cycle.sources_total,
            "degraded_sources": list(cycle.degraded_sources),
            "records_fetched_total": cycle.total_items,
        }
        if cycle.total_items == 0:
            return False

        batch = self.ingestion.ingest(cycle.items)
        inserted = tuple(
            outcome.item
            for outcome in batch.outcomes
            if outcome.inserted and outcome.item is not None
        )
        self._last_activity["ingestion"] = {
            "total_records": batch.total_records,
            "inserted_count": batch.inserted_count,
            "duplicate_count": batch.duplicate_count,
        }
        if not inserted:
            return False

        tag_result = self.tagging.tag_items(inserted)
        summary = self.summarizer.summarize_window(
            symbol_scope="GLOBAL",
            window_start=_utc_now_iso(),
            window_end=_utc_now_iso(),
            items=inserted,
            tags=tag_result.tags,
            max_items=5,
        )
        self._last_activity["tagging"] = {
            "tagged_items": tag_result.tagged_items,
        }
        self._last_activity["summary"] = {
            "summary_id": summary.summary_id,
            "source_count": len(summary.source_news_ids),
            "token_count": summary.token_count,
        }
        return True

    def activity_snapshot(self) -> dict[str, Any]:
        return dict(self._last_activity)

    def _fetch_mock_records(self, *, since: str | None, limit: int) -> list[dict[str, Any]]:
        _ = since
        if limit <= 0:
            return []
        now_iso = _utc_now_iso()
        return [
            {
                "source": "mock.crypto",
                "source_item_id": f"mock-{int(time.time())}",
                "published_at": now_iso,
                "title": "Bitcoin volatility cools as ETF inflows stabilize",
                "url": "https://example.local/news/mock-bitcoin",
                "content": "Risk appetite improves and exchange flows normalize.",
                "metadata": {"language": "en"},
            }
        ]

    def _fetch_rss_records(self, *, feed_url: str, since: str | None, limit: int) -> list[dict[str, Any]]:
        _ = since
        if limit <= 0:
            return []
        rss_xml = _helpers._http_get_text(feed_url, timeout_seconds=self.fetch_timeout_seconds)
        return _helpers._parse_rss_items(feed_url=feed_url, rss_xml=rss_xml, limit=limit)
