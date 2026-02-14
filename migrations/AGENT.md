# AGENT.md

## Responsibility

Owns schema evolution for Postgres/Timescale data domains.

## Architectural Boundaries

- Migration scripts only.
- No application business logic beyond data transformation intent.

## Coding Conventions

- Reversible migrations where practical.
- Explicit indexes, constraints, and comments for non-obvious DDL.

## Dependency Rules

- Migrations must track ordered revision graph.
- Runtime services depend on migrated schema contracts.

## Extension Rules

- New tables/columns require matching model/repository and test updates.

## Integration Contracts

- Schema must stay compatible with contract-level payload structures.

## Testing Expectations

- Migration history checks and basic upgrade/downgrade validation are required.

## Operational Notes

- Avoid destructive changes without staged rollout and rollback strategy.
