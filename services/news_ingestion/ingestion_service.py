from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Protocol
import uuid

from services.news_ingestion.source_connectors import NewsSourceRecord


@dataclass(frozen=True, slots=True)
class NormalizedNewsItem:
    news_id: str
    source: str
    source_item_id: str
    url: str
    title: str
    body: str | None
    published_at: str
    ingested_at: str
    content_hash: str
    language: str
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class NewsIngestionOutcome:
    source: str
    source_item_id: str
    inserted: bool
    dedupe_reason: str | None
    item: NormalizedNewsItem | None


@dataclass(frozen=True, slots=True)
class NewsIngestionBatchResult:
    total_records: int
    inserted_count: int
    duplicate_count: int
    outcomes: tuple[NewsIngestionOutcome, ...]


class NewsIngestionError(ValueError):
    """Raised when incoming news records cannot be normalized safely."""


class NewsItemStore(Protocol):
    def has_source_item(self, *, source: str, source_item_id: str) -> bool: ...

    def has_hash(self, *, content_hash: str) -> bool: ...

    def persist_item(self, item: NormalizedNewsItem) -> None: ...


class InMemoryNewsItemStore:
    """In-memory `news_items`-like store for deterministic tests and local flow validation."""

    def __init__(self) -> None:
        self._items_by_source_item: dict[tuple[str, str], NormalizedNewsItem] = {}
        self._hashes: set[str] = set()

    def has_source_item(self, *, source: str, source_item_id: str) -> bool:
        return (source, source_item_id) in self._items_by_source_item

    def has_hash(self, *, content_hash: str) -> bool:
        return content_hash in self._hashes

    def persist_item(self, item: NormalizedNewsItem) -> None:
        self._items_by_source_item[(item.source, item.source_item_id)] = item
        self._hashes.add(item.content_hash)

    def list_items(self) -> tuple[NormalizedNewsItem, ...]:
        return tuple(self._items_by_source_item.values())


class NewsIngestionService:
    """Normalizes source records and persists deduplicated news items."""

    def __init__(
        self,
        *,
        store: NewsItemStore,
        uuid_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
        now_factory: Callable[[], str] = lambda: _utc_now_iso(),
    ) -> None:
        self._store = store
        self._uuid_factory = uuid_factory
        self._now_factory = now_factory

    def ingest(self, records: Iterable[NewsSourceRecord]) -> NewsIngestionBatchResult:
        outcomes: list[NewsIngestionOutcome] = []
        inserted_count = 0
        duplicate_count = 0

        for record in records:
            normalized = self._normalize_record(record)
            dedupe_reason: str | None = None
            inserted = False

            if self._store.has_source_item(
                source=normalized.source,
                source_item_id=normalized.source_item_id,
            ):
                dedupe_reason = "duplicate_source_item"
            elif self._store.has_hash(content_hash=normalized.content_hash):
                dedupe_reason = "duplicate_hash"
            else:
                self._store.persist_item(normalized)
                inserted = True
                inserted_count += 1

            if not inserted:
                duplicate_count += 1

            outcomes.append(
                NewsIngestionOutcome(
                    source=normalized.source,
                    source_item_id=normalized.source_item_id,
                    inserted=inserted,
                    dedupe_reason=dedupe_reason,
                    item=normalized if inserted else None,
                )
            )

        return NewsIngestionBatchResult(
            total_records=len(outcomes),
            inserted_count=inserted_count,
            duplicate_count=duplicate_count,
            outcomes=tuple(outcomes),
        )

    def _normalize_record(self, record: NewsSourceRecord) -> NormalizedNewsItem:
        source = record.source.strip()
        source_item_id = record.source_item_id.strip()
        title = record.title.strip()
        url = (record.url or "").strip()
        published_at = record.published_at.strip()

        if not source:
            raise NewsIngestionError("record.source must be non-empty")
        if not source_item_id:
            raise NewsIngestionError("record.source_item_id must be non-empty")
        if not title:
            raise NewsIngestionError("record.title must be non-empty")
        if not url:
            raise NewsIngestionError("record.url must be non-empty")
        if not published_at:
            raise NewsIngestionError("record.published_at must be non-empty")

        body = (record.content or "").strip() or None
        metadata = record.metadata if isinstance(record.metadata, Mapping) else {}
        language = str(metadata.get("language", "en")).strip().lower() or "en"
        content_hash = _content_hash(title=title, body=body, url=url)
        ingested_at = self._now_factory()

        raw_payload = {
            "source": source,
            "source_item_id": source_item_id,
            "url": url,
            "title": title,
            "content": body or "",
            "published_at": published_at,
            "metadata": dict(metadata),
        }

        return NormalizedNewsItem(
            news_id=self._uuid_factory(),
            source=source,
            source_item_id=source_item_id,
            url=url,
            title=title,
            body=body,
            published_at=published_at,
            ingested_at=ingested_at,
            content_hash=content_hash,
            language=language,
            raw_payload=raw_payload,
        )


def _content_hash(*, title: str, body: str | None, url: str) -> str:
    _ = url  # URL is intentionally excluded so content dedupe can collapse cross-source copies.
    payload = "\n".join((title.strip(), (body or "").strip()))
    return sha256(payload.encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
