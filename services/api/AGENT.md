# AGENT.md

## Responsibility

Hosts control-plane APIs for strategy, risk, replay, governance, and operations.

## Architectural Boundaries

- API handlers coordinate services and persistence boundaries.
- Business core rules should stay in domain services, not controllers.
- Control-plane state adapters may compose OMS/risk contracts but must not re-implement risk math.

## Coding Conventions

- Use explicit request/response schemas and typed errors.
- Keep endpoint behavior idempotent where practical.
- Keep auth/RBAC checks in dependencies, not inline in handlers.

## Dependency Rules

- API may depend on orchestrator/OMS/risk/query adapters.
- API may depend on LLM governance and replay services for observability endpoints.
- Avoid direct infrastructure-specific logic in route handlers.

## Extension Rules

- New endpoints require auth/RBAC, validation, and audit considerations.

## Integration Contracts

- Expose stable API contracts for UI and operators.
- `app.py` owns FastAPI app factory and router registration.
- `auth.py` owns JWT bearer parsing and `viewer/operator/admin` dependency gates.
- `state.py` owns in-memory control-plane/trading-ops adapters, governance aggregates, replay request cache, and risk-control action wiring.
- `routers/system.py` exposes liveness/readiness/metadata.
- `routers/control.py` exposes mode and strategy state controls.
- `routers/ops.py` exposes orders, positions, portfolio, risk status, and kill-switch/circuit-breaker actions.
- `routers/governance.py` exposes LLM usage/quota/breach history endpoints.
- `routers/replay.py` exposes replay request submission and decision replay retrieval endpoints.
- `routers/dashboard.py` exposes lightweight operator dashboard pages (`/dashboard/*`).

## Testing Expectations

- Contract tests, RBAC tests, and error-path coverage are mandatory.
- Validate role boundaries (`viewer`, `operator`, `admin`) for every mutating endpoint.
- Validate replay/governance not-found and filtering behaviors, and dashboard HTML route availability.

## Operational Notes

- Include health/readiness endpoints and clear error observability.
