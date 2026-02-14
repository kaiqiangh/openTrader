# AGENT.md

## Responsibility

Owns cross-stream integrity checks, anomaly detection, and recovery signal generation.

## Architectural Boundaries

- Focus on data quality and integrity enforcement.
- Must not take direct execution actions.

## Coding Conventions

- Integrity rules should be explicit, deterministic, and explainable.

## Dependency Rules

- Consume normalized market feeds and persistence snapshots.
- Emit integrity events through messaging contracts.

## Extension Rules

- New checks require severity mapping and remediation hints.

## Integration Contracts

- Integrates with ingestion and notification pipelines for incident signaling.

## Testing Expectations

- Fault-injection and edge-case validation tests are required.

## Operational Notes

- Integrity alert noise must be controlled with dedupe/coalescing strategy.
