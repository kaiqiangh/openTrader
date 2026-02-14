# AGENT.md

## Responsibility

Collects and normalizes external news/social content for downstream summarization.

## Architectural Boundaries

- Owns source connector logic and dedup normalization.
- Owns ingestion normalization + dedupe persistence contracts for `news_items`.
- Owns tagging/relevance scoring contracts for `news_tags`.
- Owns quality metric snapshots for ingestion coverage/freshness/error visibility.
- Must not implement strategy decisioning.
- Connector failures must be isolated so one source outage does not block other sources.

## Coding Conventions

- Preserve source metadata and dedupe fingerprints.
- Keep connector identity (`connector_id`, `connector_kind`) explicit in normalized outputs.
- Keep dedupe reasons explicit (`duplicate_source_item`, `duplicate_hash`) for observability.

## Dependency Rules

- Source adapters should be pluggable and isolated.
- Persistence must flow through store protocols, not hard-coded DB clients in core logic.

## Extension Rules

- New source connectors require reliability and rate-limit handling.

## Integration Contracts

- Emits normalized news records for persistence/tagging/summarization.
- `source_connectors.py` provides protocol, registry, and cycle runner contracts for RSS/API/social sources.
- `ingestion_service.py` provides normalized item contracts and dedupe-aware ingest workflow.
- `tagging_relevance.py` provides symbol/topic/relevance/sentiment tagging contracts.
- `quality_metrics.py` provides counters + quality snapshot contracts consumed by dashboard/ops surfaces.

## Testing Expectations

- Include connector-level parsing and dedupe tests.
- Include quality metric snapshot tests for freshness/coverage/lag/error calculations.

## Operational Notes

- Source outages must degrade gracefully without blocking trading pipeline.
