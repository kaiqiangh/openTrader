# AGENT.md

## Responsibility

Defines verification strategy for contracts, domain logic, integrations, and operational guarantees.

## Architectural Boundaries

- Tests validate behavior; they do not become production configuration sources.

## Coding Conventions

- Keep tests deterministic, isolated, and explicit about expected behavior.
- Prefer domain-focused fixtures over opaque global state.

## Dependency Rules

- Unit tests should avoid external infrastructure.
- Integration tests should use real infra dependencies where contract confidence is required.

## Extension Rules

- New features must include tests for happy path, failure path, and boundary conditions.

## Integration Contracts

- Validate message envelope, topology, and persistence interfaces as first-class contracts.

## Testing Expectations

- Maintain strong coverage for risk gates, mode isolation, idempotency, and replay determinism.

## Operational Notes

- Distinguish fast unit suites from slower integration suites in CI targets.
