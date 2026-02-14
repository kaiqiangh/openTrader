# AGENT.md

## Responsibility

Defines cross-service message contract schemas.

## Architectural Boundaries

- Contract definitions only.
- No service-specific workflow logic.

## Coding Conventions

- Use strict schema constraints and explicit required fields.
- Keep naming consistent with event envelope conventions.

## Dependency Rules

- Shared validator code may depend on these schemas.
- Do not reference implementation modules from contracts.

## Extension Rules

- Treat schema changes as versioned contract changes.
- Preserve backward compatibility unless coordinated breaking upgrade is approved.

## Integration Contracts

- Message envelope schema is authoritative for cross-service events.

## Testing Expectations

- Add tests for required fields, enum constraints, and invalid payload rejection.

## Operational Notes

- Coordinate schema changes with producer/consumer rollout windows.
