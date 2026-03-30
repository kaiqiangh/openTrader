from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Final, Literal, Mapping, Protocol

ConnectorKind = Literal["rss", "api", "social", "custom"]
_ALLOWED_KINDS: Final[frozenset[str]] = frozenset({"rss", "api", "social", "custom"})


@dataclass(frozen=True, slots=True)
class NewsSourceRecord:
    source: str
    source_item_id: str
    published_at: str
    title: str
    url: str | None = None
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConnectorFetchResult:
    source: str
    connector_kind: str
    items: tuple[NewsSourceRecord, ...]
    degraded: bool
    error: str | None
    fetched_at: str


@dataclass(frozen=True, slots=True)
class ConnectorCycleResult:
    results: tuple[ConnectorFetchResult, ...]
    items: tuple[NewsSourceRecord, ...]
    total_items: int
    sources_total: int
    degraded_sources: tuple[str, ...]


class NewsSourceConnector(Protocol):
    connector_id: str
    connector_kind: str

    def fetch(self, *, since: str | None, limit: int) -> ConnectorFetchResult: ...


class ConnectorRegistrationError(ValueError):
    """Raised when connector registration fails."""


class ConnectorNotFoundError(KeyError):
    """Raised when connector lookup fails."""


FetchCallable = Callable[..., Iterable[NewsSourceRecord | Mapping[str, Any]]]


class CallableSourceConnector:
    """Connector wrapper for source-specific callables (RSS/API/social/custom)."""

    def __init__(
        self,
        *,
        connector_id: str,
        connector_kind: ConnectorKind,
        fetcher: FetchCallable,
    ) -> None:
        normalized_id = connector_id.strip()
        normalized_kind = connector_kind.strip().lower()
        if not normalized_id:
            raise ConnectorRegistrationError("connector_id must be non-empty")
        if normalized_kind not in _ALLOWED_KINDS:
            raise ConnectorRegistrationError(
                f"unsupported connector_kind: {connector_kind}; allowed={sorted(_ALLOWED_KINDS)}"
            )

        self.connector_id = normalized_id
        self.connector_kind = normalized_kind
        self._fetcher = fetcher

    def fetch(self, *, since: str | None, limit: int) -> ConnectorFetchResult:
        if limit <= 0:
            raise ValueError("limit must be positive")

        raw_items = tuple(self._fetcher(since=since, limit=limit))
        normalized_items = tuple(
            _normalize_record(item=item, default_source=self.connector_id) for item in raw_items
        )
        return ConnectorFetchResult(
            source=self.connector_id,
            connector_kind=self.connector_kind,
            items=normalized_items,
            degraded=False,
            error=None,
            fetched_at=_utc_now_iso(),
        )


class SourceConnectorRegistry:
    """Registry for pluggable source connectors."""

    def __init__(self) -> None:
        self._connectors: dict[str, NewsSourceConnector] = {}

    def register(self, connector: NewsSourceConnector) -> None:
        if connector.connector_id in self._connectors:
            raise ConnectorRegistrationError(
                f"connector already registered: {connector.connector_id}"
            )
        self._connectors[connector.connector_id] = connector

    def get(self, connector_id: str) -> NewsSourceConnector:
        connector = self._connectors.get(connector_id)
        if connector is None:
            raise ConnectorNotFoundError(f"connector not found: {connector_id}")
        return connector

    def list_connector_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._connectors.keys()))

    def list_connectors(self) -> tuple[NewsSourceConnector, ...]:
        return tuple(self._connectors[key] for key in self.list_connector_ids())


class NewsSourceConnectorFramework:
    """Runs source connector fetch cycles with fault isolation per source."""

    def __init__(self, *, registry: SourceConnectorRegistry) -> None:
        self._registry = registry

    def fetch_cycle(
        self,
        *,
        since: str | None = None,
        limit_per_source: int = 100,
        source_filter: tuple[str, ...] | None = None,
    ) -> ConnectorCycleResult:
        if limit_per_source <= 0:
            raise ValueError("limit_per_source must be positive")

        filter_set = set(source_filter or ())
        selected = [
            connector
            for connector in self._registry.list_connectors()
            if not filter_set or connector.connector_id in filter_set
        ]

        results: list[ConnectorFetchResult] = []
        all_items: list[NewsSourceRecord] = []
        degraded_sources: list[str] = []

        for connector in selected:
            try:
                result = connector.fetch(since=since, limit=limit_per_source)
            except Exception as exc:  # noqa: BLE001 - framework must isolate source faults
                result = ConnectorFetchResult(
                    source=connector.connector_id,
                    connector_kind=connector.connector_kind,
                    items=(),
                    degraded=True,
                    error=f"{exc.__class__.__name__}: {exc}",
                    fetched_at=_utc_now_iso(),
                )

            results.append(result)
            all_items.extend(result.items)
            if result.degraded:
                degraded_sources.append(result.source)

        return ConnectorCycleResult(
            results=tuple(results),
            items=tuple(all_items),
            total_items=len(all_items),
            sources_total=len(results),
            degraded_sources=tuple(degraded_sources),
        )


def _normalize_record(
    *,
    item: NewsSourceRecord | Mapping[str, Any],
    default_source: str,
) -> NewsSourceRecord:
    if isinstance(item, NewsSourceRecord):
        record = item
    else:
        source = str(item.get("source", default_source)).strip() or default_source
        source_item_id = str(item.get("source_item_id", "")).strip()
        published_at = str(item.get("published_at", "")).strip() or _utc_now_iso()
        title = str(item.get("title", "")).strip()
        record = NewsSourceRecord(
            source=source,
            source_item_id=source_item_id,
            published_at=published_at,
            title=title,
            url=str(item.get("url")).strip() if item.get("url") is not None else None,
            content=str(item.get("content", "")),
            metadata=dict(item.get("metadata", {}))
            if isinstance(item.get("metadata"), Mapping)
            else {},
        )

    if not record.source.strip():
        raise ValueError("record.source must be non-empty")
    if not record.source_item_id.strip():
        raise ValueError("record.source_item_id must be non-empty")
    if not record.title.strip():
        raise ValueError("record.title must be non-empty")
    if not record.published_at.strip():
        raise ValueError("record.published_at must be non-empty")

    return record


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
