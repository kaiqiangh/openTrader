# AGENT.md

## Responsibility

Collects and normalizes external news/social content for downstream summarization.

## Architectural Boundaries

- Owns source connector logic and dedup normalization.
- Must not implement strategy decisioning.
- Connector failures must be isolated so one source outage does not block other sources.

## Coding Conventions

- Preserve source metadata and dedupe fingerprints.
- Keep connector identity (`connector_id`, `connector_kind`) explicit in normalized outputs.

## Dependency Rules

- Source adapters should be pluggable and isolated.

## Extension Rules

- New source connectors require reliability and rate-limit handling.

## Integration Contracts

- Emits normalized news records for persistence/tagging/summarization.
- `source_connectors.py` provides protocol, registry, and cycle runner contracts for RSS/API/social sources.

## Testing Expectations

- Include connector-level parsing and dedupe tests.

## Operational Notes

- Source outages must degrade gracefully without blocking trading pipeline.
