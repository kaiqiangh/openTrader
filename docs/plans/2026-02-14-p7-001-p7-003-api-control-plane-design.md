# Phase 7 Control Plane API Design (P7-001 to P7-003)

## Scope

Deliver the first API control-plane slice:

- `P7-001`: FastAPI service baseline with auth, mode/strategy controls, health/readiness, and metadata.
- `P7-002`: RBAC enforcement with `viewer`, `operator`, `admin` roles.
- `P7-003`: Trading operations endpoints for orders, positions, portfolio snapshots, risk status, and circuit-breaker/kill-switch controls.

## Context

- `services/api/` currently contains scaffold files only.
- OMS/risk domain logic already exists in `services/oms/` and must remain authoritative.
- ARD mandates JWT auth and RBAC role boundaries.

## Approaches Considered

### Option A (Recommended): In-memory FastAPI control plane with strict DI boundaries

- Build FastAPI app with typed routers and dependency-injected auth/RBAC/state providers.
- Keep all business logic in small state/service helpers that adapt existing OMS contracts.
- Provide deterministic in-memory runtime state for tests and local bootstrap.

Pros:
- Fastest path to executable API baseline with clean extension path to DB adapters.
- Keeps domain logic out of route handlers.
- Enables strong contract tests now.

Cons:
- State is process-local and not yet persistent.

### Option B: Direct DB-backed API now

Pros:
- Closer to production persistence from day one.

Cons:
- Larger scope and migration complexity for this phase boundary.
- Slower iteration and harder isolated testing.

### Option C: API stubs with mocked responses only

Pros:
- Minimal implementation effort.

Cons:
- Fails runtime expectations for control and risk operations.

## Selected Design

Option A.

### Module boundaries

- `services/api/app.py`: FastAPI app factory, lifespan, router registration.
- `services/api/settings.py`: environment-backed API settings.
- `services/api/auth.py`: JWT bearer parsing + RBAC dependency guards.
- `services/api/state.py`: in-memory control-plane state and adapters to OMS/risk contracts.
- `services/api/models.py`: Pydantic request/response contracts.
- `services/api/routers/system.py`: liveness/readiness/metadata endpoints.
- `services/api/routers/control.py`: mode and strategy control endpoints.
- `services/api/routers/ops.py`: orders/positions/portfolio/risk endpoints and risk control actions.

### RBAC model

- `viewer`: read-only endpoints (`GET` metadata/control/ops).
- `operator`: mode updates, strategy state updates, circuit-breaker trip/reset.
- `admin`: all operator actions plus kill-switch enable/disable.

### Data flow

1. Request enters FastAPI router.
2. Bearer JWT is validated and role extracted.
3. RBAC dependency authorizes or rejects.
4. Route delegates to state/service helper.
5. Helper updates or reads domain state and returns typed response model.

### Error handling

- Invalid/expired/malformed JWT => `401`.
- Role violation => `403`.
- Invalid state transition (mode/strategy/control command) => `422`/`400` with explicit detail.
- Missing portfolio snapshot => `404`.

### Testing strategy

- Auth + RBAC tests for role-based access and denial paths.
- Control-plane tests for mode/strategy endpoints.
- Trading ops tests for list/read/control endpoints.
- Documentation/plan status tests for `P7-001..P7-003` alignment.

## Success Criteria

- New API modules under `services/api/` are executable and covered by tests.
- `P7-001`, `P7-002`, `P7-003` marked `DONE` in `docs/IMPLEMENTATION_PLAN.md`.
- README and service AGENT docs reflect API baseline modules and contracts.
- `uv run pytest -q`, `uv run ruff check .`, and Go tests remain green.
