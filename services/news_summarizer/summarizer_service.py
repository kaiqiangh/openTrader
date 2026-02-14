from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
import uuid

from services.news_ingestion.ingestion_service import NormalizedNewsItem
from services.news_ingestion.tagging_relevance import NewsTag


@dataclass(frozen=True, slots=True)
class NewsSummaryArtifact:
    summary_id: str
    symbol_scope: str
    window_start: str
    window_end: str
    summary_text: str
    token_count: int
    generated_at: str
    source_news_ids: tuple[str, ...]


class NewsSummaryStore(Protocol):
    def persist_summary(self, summary: NewsSummaryArtifact) -> None: ...


class InMemoryNewsSummaryStore:
    """In-memory `news_summaries`-like store for deterministic tests and local flow validation."""

    def __init__(self) -> None:
        self._summaries: list[NewsSummaryArtifact] = []

    def persist_summary(self, summary: NewsSummaryArtifact) -> None:
        self._summaries.append(summary)

    def list_summaries(self) -> tuple[NewsSummaryArtifact, ...]:
        return tuple(self._summaries)


class RollingNewsSummarizer:
    """Builds deterministic rolling summaries by symbol scope and time window."""

    def __init__(
        self,
        *,
        store: NewsSummaryStore,
        uuid_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
        now_factory: Callable[[], str] = lambda: _utc_now_iso(),
    ) -> None:
        self._store = store
        self._uuid_factory = uuid_factory
        self._now_factory = now_factory

    def summarize_window(
        self,
        *,
        symbol_scope: str,
        window_start: str,
        window_end: str,
        items: Iterable[NormalizedNewsItem],
        tags: Iterable[NewsTag],
        max_items: int = 5,
    ) -> NewsSummaryArtifact:
        if max_items <= 0:
            raise ValueError("max_items must be positive")

        scope = symbol_scope.strip().upper() or "GLOBAL"
        item_map = {item.news_id: item for item in items}

        scoped_tags = [
            tag
            for tag in tags
            if _tag_matches_scope(scope=scope, tag=tag)
        ]
        scoped_tags.sort(key=lambda tag: (tag.relevance_score, tag.sentiment_score, tag.news_id), reverse=True)

        selected_news_ids: list[str] = []
        for tag in scoped_tags:
            if tag.news_id in selected_news_ids:
                continue
            if tag.news_id not in item_map:
                continue
            selected_news_ids.append(tag.news_id)
            if len(selected_news_ids) >= max_items:
                break

        summary_text = "news_unavailable"
        if selected_news_ids:
            selected_tags = [tag for tag in scoped_tags if tag.news_id in selected_news_ids]
            avg_relevance = sum(tag.relevance_score for tag in selected_tags) / len(selected_tags)
            avg_sentiment = sum(tag.sentiment_score for tag in selected_tags) / len(selected_tags)
            headlines = "; ".join(item_map[news_id].title for news_id in selected_news_ids)
            summary_text = (
                f"{scope} news from {window_start} to {window_end}: {len(selected_news_ids)} items. "
                f"Top headlines: {headlines}. avg_relevance={avg_relevance:.2f}, "
                f"avg_sentiment={avg_sentiment:.2f}."
            )

        artifact = NewsSummaryArtifact(
            summary_id=self._uuid_factory(),
            symbol_scope=scope,
            window_start=window_start,
            window_end=window_end,
            summary_text=summary_text,
            token_count=len(summary_text.split()),
            generated_at=self._now_factory(),
            source_news_ids=tuple(selected_news_ids),
        )
        self._store.persist_summary(artifact)
        return artifact


def _tag_matches_scope(*, scope: str, tag: NewsTag) -> bool:
    if scope == "GLOBAL":
        return True

    if tag.symbol is None:
        return False

    return tag.symbol.upper() == scope


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
