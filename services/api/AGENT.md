# AGENT.md

## Responsibility

Hosts control-plane APIs for strategy, risk, replay, governance, and operations.

## Architectural Boundaries

- API handlers coordinate services and persistence boundaries.
- Business core rules should stay in domain services, not controllers.

## Coding Conventions

- Use explicit request/response schemas and typed errors.
- Keep endpoint behavior idempotent where practical.

## Dependency Rules

- API may depend on orchestrator/OMS/risk/query adapters.
- Avoid direct infrastructure-specific logic in route handlers.

## Extension Rules

- New endpoints require auth/RBAC, validation, and audit considerations.

## Integration Contracts

- Expose stable API contracts for UI and operators.

## Testing Expectations

- Contract tests, RBAC tests, and error-path coverage are mandatory.

## Operational Notes

- Include health/readiness endpoints and clear error observability.
