# Phase 7 Governance + Replay + Dashboard Design (P7-004 to P7-006)

## Scope

Deliver the next Phase 7 tasks on top of the existing FastAPI control-plane baseline:

- `P7-004`: LLM governance endpoints (usage/cost/quota/breach history).
- `P7-005`: replay request and decision-trace retrieval endpoints.
- `P7-006`: dashboard shell with navigation and live status pages.

## Context

- `services/api/` already has auth/RBAC, system/control/ops routers.
- LLM governance contracts exist in `services/llm_gateway/` and replay contracts exist in `services/agent_orchestrator/replay_service.py`.
- Current API state uses in-memory adapters; this turn should keep compatibility with that baseline.

## Approaches Considered

### Option A (Recommended): Extend API with in-memory governance/replay adapters + HTML dashboard shell

- Add routers for governance, replay, and dashboard.
- Add typed Pydantic contracts for governance and replay responses.
- Extend control-plane state with governance/replay records and async adapter methods.

Pros:
- Fastest executable path with testable API contracts.
- Reuses existing domain contracts and keeps handlers thin.
- Enables immediate operator-visible dashboard shell without frontend stack commitment.

Cons:
- In-memory persistence only until later DB-backed API iterations.

### Option B: Build DB-backed endpoints immediately

Pros:
- More production-like data lifecycle.

Cons:
- Larger migration scope and slower iteration.
- More operational coupling before contract surfaces stabilize.

### Option C: Ship API JSON only and defer dashboard shell

Pros:
- Less implementation overhead.

Cons:
- Misses explicit `P7-006` deliverable.

## Selected Design

Option A.

### Module boundaries

- `services/api/routers/governance.py`
  - `GET /governance/llm/usage`
  - `GET /governance/llm/breaches`

- `services/api/routers/replay.py`
  - `POST /replay/requests`
  - `GET /replay/requests/{request_id}`
  - `GET /replay/decisions/{decision_id}`

- `services/api/routers/dashboard.py`
  - `GET /dashboard`
  - `GET /dashboard/status`
  - `GET /dashboard/governance`
  - `GET /dashboard/replay`

- `services/api/state.py`
  - In-memory governance aggregate views (usage/quota/breach)
  - Replay trace adapters compatible with `DecisionReplayService`
  - Replay request cache

- `services/api/models.py`
  - New governance and replay request/response schemas.

### RBAC policy

- Governance and replay read/retrieve endpoints: `viewer`+.
- Replay request endpoint (`POST /replay/requests`): `viewer`+ (read-style operation with cached request metadata).
- Dashboard pages: `viewer`+.

### Data flow

1. Governance endpoints aggregate `LLMCallRecord` and quota-limit records by `(strategy_id, agent_name)`.
2. Replay endpoints map API requests to `DecisionReplayService` via in-memory adapters.
3. Dashboard pages render HTML views over existing control-plane, governance, and replay endpoint data.

### Error handling

- Missing/invalid JWT => `401`, insufficient role => `403`.
- Replay decision not found => `404`.
- Unknown replay request ID => `404`.

### Testing

- Add tests for governance endpoints (usage/breach payloads + auth behavior).
- Add tests for replay request/retrieval endpoints and not-found path.
- Add tests for dashboard shell HTML responses and key navigation/status sections.
- Keep docs tests aligned with new modules and plan statuses.

## Success Criteria

- `P7-004`, `P7-005`, and `P7-006` marked `DONE` in `docs/IMPLEMENTATION_PLAN.md`.
- New API tests pass plus full `pytest`, `ruff`, and Go tests remain green.
- README and API AGENT docs include new governance/replay/dashboard modules.
