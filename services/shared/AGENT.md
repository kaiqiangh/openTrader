# AGENT.md

## Responsibility

Holds shared contracts and utility types used across service modules.

## Architectural Boundaries

- Shared abstractions only.
- No business-domain state transitions or external side effects.

## Coding Conventions

- Keep shared APIs minimal and stable.
- Prefer explicit validation helpers for cross-service contracts.

## Dependency Rules

- All services may depend on shared contracts.
- Shared package must not import service-specific modules.

## Extension Rules

- Shared additions must be broadly reusable and avoid domain leakage.

## Integration Contracts

- Message envelope validator is authoritative for base event metadata.

## Testing Expectations

- Validate positive and negative contract cases.

## Operational Notes

- Treat breaking changes as high-impact and coordinate rollout.
