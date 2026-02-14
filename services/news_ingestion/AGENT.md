# AGENT.md

## Responsibility

Collects and normalizes external news/social content for downstream summarization.

## Architectural Boundaries

- Owns source connector logic and dedup normalization.
- Must not implement strategy decisioning.

## Coding Conventions

- Preserve source metadata and dedupe fingerprints.

## Dependency Rules

- Source adapters should be pluggable and isolated.

## Extension Rules

- New source connectors require reliability and rate-limit handling.

## Integration Contracts

- Emits normalized news records for persistence/tagging/summarization.

## Testing Expectations

- Include connector-level parsing and dedupe tests.

## Operational Notes

- Source outages must degrade gracefully without blocking trading pipeline.
