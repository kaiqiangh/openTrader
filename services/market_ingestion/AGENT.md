# AGENT.md

## Responsibility

Ingests exchange market data, normalizes payloads, validates integrity, and emits canonical market events.

## Architectural Boundaries

- Owns ingestion adapters, sync/recovery logic, normalization, and ingestion metrics.
- Must not own strategy decision logic or order lifecycle state.

## Coding Conventions

- Normalize external payloads into typed internal contracts first.
- Keep sequence and timestamp handling explicit and testable.

## Dependency Rules

- May depend on shared envelope/contracts.
- Broker and persistence adapters should be injected behind interfaces.

## Extension Rules

- New exchange support must implement snapshot bootstrap and delta semantics.
- Integrity rules must be additive and backward-compatible where feasible.

## Integration Contracts

- Publishes canonical events to the market routing contract.
- Persistence writers map normalized records to timeseries schema.

## Testing Expectations

- Unit tests for normalization and integrity edge cases.
- Integration tests for snapshot+delta replay and deterministic outputs.

## Operational Notes

- Reconnect, stale detection, and resync behavior are operationally critical paths.
