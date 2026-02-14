# AGENT.md

## Responsibility

Defines RabbitMQ exchanges, queues, bindings, and DLQ topology.

## Architectural Boundaries

- Topology declaration only.
- No consumer or publisher runtime logic here.

## Coding Conventions

- Use explicit exchange type, durability, and routing keys.
- Keep DLQ routing keys deterministic and traceable.

## Dependency Rules

- Runtime services must implement behavior consistent with this topology.
- Avoid environment-specific hard-coding inside topology JSON.

## Extension Rules

- Add queues with matching DLQ policy by default.
- Update bindings and docs in the same change.

## Integration Contracts

- Routing keys must match producer event types and consumer subscriptions.

## Testing Expectations

- Add topology tests for required exchanges/queues/bindings and DLQ coverage.

## Operational Notes

- Topology updates should be deploy-safe and backward-compatible where possible.
