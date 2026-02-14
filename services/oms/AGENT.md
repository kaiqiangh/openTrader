# AGENT.md

## Responsibility

Manages order lifecycle state, fill reconciliation, and order event publication.

## Architectural Boundaries

- Owns lifecycle transitions and consistency checks.
- Must not bypass risk policy decisions.

## Coding Conventions

- State transitions should be explicit and validated.
- Idempotency must be enforced for repeated exchange/order events.

## Dependency Rules

- Depends on execution events, persistence adapters, and risk controls.

## Extension Rules

- Any new order state requires transition matrix and migration/test updates.

## Integration Contracts

- Publishes order updates for API, risk, replay, and notifications.

## Testing Expectations

- Transition matrix tests and reconciliation edge-case tests are required.

## Operational Notes

- Ensure eventual consistency handling for delayed exchange updates.
