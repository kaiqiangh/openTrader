from __future__ import annotations

import pytest

from services.news_ingestion.source_connectors import (
    CallableSourceConnector,
    ConnectorNotFoundError,
    ConnectorRegistrationError,
    NewsSourceConnectorFramework,
    NewsSourceRecord,
    SourceConnectorRegistry,
)


def _record(*, source: str, source_item_id: str, title: str) -> NewsSourceRecord:
    return NewsSourceRecord(
        source=source,
        source_item_id=source_item_id,
        published_at="2026-02-14T17:30:00Z",
        title=title,
        url=f"https://example.com/{source_item_id}",
        content=f"{title} body",
    )


def test_registry_registers_and_lists_connectors() -> None:
    registry = SourceConnectorRegistry()
    connector = CallableSourceConnector(
        connector_id="rss-main",
        connector_kind="rss",
        fetcher=lambda *, since, limit: (_record(source="rss-main", source_item_id="1", title="headline"),),
    )

    registry.register(connector)

    assert registry.list_connector_ids() == ("rss-main",)
    assert registry.get("rss-main").connector_kind == "rss"


def test_registry_rejects_duplicate_connector_id() -> None:
    registry = SourceConnectorRegistry()
    connector = CallableSourceConnector(
        connector_id="api-main",
        connector_kind="api",
        fetcher=lambda *, since, limit: (),
    )

    registry.register(connector)
    with pytest.raises(ConnectorRegistrationError):
        registry.register(connector)


def test_registry_raises_for_missing_connector() -> None:
    registry = SourceConnectorRegistry()

    with pytest.raises(ConnectorNotFoundError):
        registry.get("missing")


def test_framework_fetch_cycle_aggregates_multiple_sources() -> None:
    registry = SourceConnectorRegistry()
    registry.register(
        CallableSourceConnector(
            connector_id="rss-main",
            connector_kind="rss",
            fetcher=lambda *, since, limit: (_record(source="rss-main", source_item_id="1", title="rss"),),
        )
    )
    registry.register(
        CallableSourceConnector(
            connector_id="api-main",
            connector_kind="api",
            fetcher=lambda *, since, limit: (_record(source="api-main", source_item_id="2", title="api"),),
        )
    )
    registry.register(
        CallableSourceConnector(
            connector_id="social-main",
            connector_kind="social",
            fetcher=lambda *, since, limit: (_record(source="social-main", source_item_id="3", title="social"),),
        )
    )

    framework = NewsSourceConnectorFramework(registry=registry)
    cycle = framework.fetch_cycle(limit_per_source=10)

    assert cycle.sources_total == 3
    assert cycle.total_items == 3
    assert cycle.degraded_sources == ()
    assert {item.source for item in cycle.items} == {"rss-main", "api-main", "social-main"}


def test_framework_isolates_failing_connector_without_blocking_others() -> None:
    registry = SourceConnectorRegistry()
    registry.register(
        CallableSourceConnector(
            connector_id="good-source",
            connector_kind="api",
            fetcher=lambda *, since, limit: (
                _record(source="good-source", source_item_id="11", title="healthy"),
            ),
        )
    )

    def _failing_fetcher(*, since, limit):
        _ = since, limit
        raise RuntimeError("source timeout")

    registry.register(
        CallableSourceConnector(
            connector_id="bad-source",
            connector_kind="rss",
            fetcher=_failing_fetcher,
        )
    )

    framework = NewsSourceConnectorFramework(registry=registry)
    cycle = framework.fetch_cycle(limit_per_source=5)

    assert cycle.sources_total == 2
    assert cycle.total_items == 1
    assert cycle.degraded_sources == ("bad-source",)
    assert any(result.error for result in cycle.results if result.source == "bad-source")
