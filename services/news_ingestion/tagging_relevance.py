from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Protocol
import re

from services.news_ingestion.ingestion_service import NormalizedNewsItem

_SYMBOL_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "BTC": ("btc", "bitcoin", "etf"),
    "ETH": ("eth", "ethereum", "staking", "merge"),
    "SOL": ("sol", "solana"),
}

_TOPIC_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "etf": ("etf", "inflow", "outflow"),
    "security": ("hack", "exploit", "breach", "security"),
    "exchange": ("exchange", "listing", "delisting"),
    "macro": ("macro", "rates", "liquidity", "inflation"),
    "regulation": ("sec", "regulation", "regulatory"),
    "market": ("market", "volatility", "price action"),
    "protocol": ("upgrade", "fork", "protocol", "validator"),
}

_POSITIVE_WORDS: Final[frozenset[str]] = frozenset(
    {"bullish", "optimism", "surge", "strong", "approval", "growth", "demand", "stable"}
)

_NEGATIVE_WORDS: Final[frozenset[str]] = frozenset(
    {"bearish", "fear", "panic", "hack", "exploit", "risk", "liquidation", "drop"}
)


@dataclass(frozen=True, slots=True)
class NewsTag:
    news_id: str
    symbol: str | None
    topic: str
    relevance_score: float
    sentiment_score: float


@dataclass(frozen=True, slots=True)
class TaggingBatchResult:
    total_items: int
    tagged_items: int
    tags: tuple[NewsTag, ...]


class NewsTagStore(Protocol):
    def persist_tag(self, tag: NewsTag) -> None: ...


class InMemoryNewsTagStore:
    """In-memory `news_tags`-like store for deterministic tests and local flow validation."""

    def __init__(self) -> None:
        self._tags: list[NewsTag] = []

    def persist_tag(self, tag: NewsTag) -> None:
        self._tags.append(tag)

    def list_tags(self) -> tuple[NewsTag, ...]:
        return tuple(self._tags)


class NewsTaggingRelevancePipeline:
    """Assigns symbol/topic tags and baseline relevance/sentiment scores."""

    def __init__(
        self,
        *,
        store: NewsTagStore,
        symbol_keywords: dict[str, tuple[str, ...]] | None = None,
        topic_keywords: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self._store = store
        self._symbol_keywords = symbol_keywords or _SYMBOL_KEYWORDS
        self._topic_keywords = topic_keywords or _TOPIC_KEYWORDS

    def tag_items(self, items: Iterable[NormalizedNewsItem]) -> TaggingBatchResult:
        tags: list[NewsTag] = []
        total_items = 0

        for item in items:
            total_items += 1
            text = _normalize_text(item)
            symbol, symbol_hits = _best_match(text=text, keyword_map=self._symbol_keywords)
            topic, topic_hits = _best_match(text=text, keyword_map=self._topic_keywords)
            if topic is None:
                topic = "general"

            sentiment_score = _sentiment_score(text)
            relevance_score = _relevance_score(
                symbol_hits=symbol_hits,
                topic_hits=topic_hits,
                sentiment_score=sentiment_score,
                has_symbol=symbol is not None,
                has_topic=topic != "general",
            )

            tag = NewsTag(
                news_id=item.news_id,
                symbol=symbol,
                topic=topic,
                relevance_score=relevance_score,
                sentiment_score=sentiment_score,
            )
            self._store.persist_tag(tag)
            tags.append(tag)

        return TaggingBatchResult(
            total_items=total_items,
            tagged_items=len(tags),
            tags=tuple(tags),
        )


def _normalize_text(item: NormalizedNewsItem) -> str:
    return f"{item.title}\n{item.body or ''}".strip().lower()


def _best_match(*, text: str, keyword_map: dict[str, tuple[str, ...]]) -> tuple[str | None, int]:
    best_name: str | None = None
    best_hits = 0
    for name, keywords in keyword_map.items():
        hits = sum(1 for keyword in keywords if keyword in text)
        if hits > best_hits:
            best_name = name
            best_hits = hits
    return best_name, best_hits


def _sentiment_score(text: str) -> float:
    tokens = re.findall(r"[a-z0-9_]+", text)
    positive_hits = sum(1 for token in tokens if token in _POSITIVE_WORDS)
    negative_hits = sum(1 for token in tokens if token in _NEGATIVE_WORDS)
    total = positive_hits + negative_hits
    if total == 0:
        return 0.0
    score = (positive_hits - negative_hits) / total
    return max(-1.0, min(1.0, score))


def _relevance_score(
    *,
    symbol_hits: int,
    topic_hits: int,
    sentiment_score: float,
    has_symbol: bool,
    has_topic: bool,
) -> float:
    base = min(1.0, (symbol_hits * 1.2 + topic_hits + abs(sentiment_score)) / 4.0)

    if has_symbol:
        base = max(base, 0.6)
    elif has_topic:
        base = max(base, 0.35)

    return max(0.0, min(1.0, base))
