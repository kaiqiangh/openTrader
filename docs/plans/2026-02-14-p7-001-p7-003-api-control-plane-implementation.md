# Phase 7 Control Plane API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement `P7-001`, `P7-002`, and `P7-003` with a runnable FastAPI control plane, JWT+RBAC security, and trading operations endpoints.

**Architecture:** Build a modular FastAPI service with route modules (`system`, `control`, `ops`), typed Pydantic contracts, JWT bearer auth dependencies, and role-gated endpoint policies. Back routes with an in-memory control-plane state adapter that composes existing OMS/risk domain contracts.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, pytest, ruff.

---

### Task 1: Add failing tests for auth + RBAC and endpoint contracts

**Files:**
- Create: `tests/test_p7_api_control_plane.py`
- Create: `tests/test_p7_api_trading_ops.py`

**Step 1: Write the failing tests**

```python
def test_liveness_and_readiness_are_public() -> None:
    ...

def test_operator_can_update_mode_but_viewer_cannot() -> None:
    ...
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_p7_api_control_plane.py tests/test_p7_api_trading_ops.py -v`
Expected: FAIL because API modules do not exist yet.

**Step 3: Write minimal implementation skeleton**

- Add app factory, settings, auth, state, models, and routers.
- Wire route registration.

**Step 4: Run targeted tests to iterate to green**

Run: `uv run pytest tests/test_p7_api_control_plane.py tests/test_p7_api_trading_ops.py -v`
Expected: PASS.

### Task 2: Implement FastAPI service and RBAC dependencies

**Files:**
- Create: `services/api/app.py`
- Create: `services/api/settings.py`
- Create: `services/api/auth.py`
- Create: `services/api/state.py`
- Create: `services/api/models.py`
- Create: `services/api/routers/system.py`
- Create: `services/api/routers/control.py`
- Create: `services/api/routers/ops.py`
- Create: `services/api/routers/__init__.py`
- Create: `services/api/__init__.py`

**Step 1: Implement JWT auth + role dependencies**

- Parse and verify HS256 JWT tokens.
- Extract `sub` and `role` claims.
- Enforce role gates via dependency factories.

**Step 2: Implement control-plane endpoints**

- `GET /health/liveness`
- `GET /health/readiness`
- `GET /metadata`
- `GET /control/mode`
- `PUT /control/mode`
- `GET /control/strategies`
- `PUT /control/strategies/{strategy_id}/state`

**Step 3: Implement trading ops endpoints**

- `GET /ops/orders`
- `GET /ops/positions`
- `GET /ops/portfolio/latest`
- `GET /ops/risk/status`
- `POST /ops/risk/circuit-breaker/trip`
- `POST /ops/risk/circuit-breaker/reset`
- `POST /ops/risk/kill-switch/enable`
- `POST /ops/risk/kill-switch/disable`

**Step 4: Validate tests**

Run: `uv run pytest tests/test_p7_api_control_plane.py tests/test_p7_api_trading_ops.py -v`
Expected: PASS.

### Task 3: Update dependencies and documentation

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `README.md`
- Modify: `services/api/AGENT.md`
- Create: `tests/test_p7_api_docs.py`
- Modify: `docs/real_execution_go_baseline.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

**Step 1: Add required packages**

- Add `fastapi` runtime dependency.
- Add `httpx` dev dependency for FastAPI test client.

**Step 2: Update docs and docs test**

- Add API baseline section to README.
- Update service AGENT boundaries/contracts with implemented modules.
- Add docs test for file presence + plan status.

**Step 3: Mark plan progress**

- Append progress ledger row and turn update.
- Mark `P7-001`, `P7-002`, `P7-003` as `DONE`.
- Move immediate next actions to `P7-004`, `P7-005`, `P7-006`.

### Task 4: Continuous Learning v2 capture

**Files:**
- Create: `docs/learning/2026-02-14-p7-control-plane-api-instincts.md`

**Step 1: Record atomic instincts**

- Capture auth boundary, RBAC policy, and control-plane API design instincts.
- Include confidence and evidence from implemented modules/tests.

### Task 5: Full verification

**Step 1: Run verification suite**

Run:
- `uv run pytest -q`
- `uv run ruff check .`
- `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`

Expected: PASS.

---

## Execution Log

- 2026-02-14: Plan created.
- 2026-02-14: Design recorded in `docs/plans/2026-02-14-p7-001-p7-003-api-control-plane-design.md`.
- 2026-02-14: Implementation started in this session.
- 2026-02-14: Added failing tests:
  - `tests/test_p7_api_control_plane.py`
  - `tests/test_p7_api_trading_ops.py`
  - `tests/test_p7_api_docs.py`
- 2026-02-14: Implemented API modules:
  - `services/api/app.py`
  - `services/api/settings.py`
  - `services/api/auth.py`
  - `services/api/state.py`
  - `services/api/models.py`
  - `services/api/dependencies.py`
  - `services/api/routers/system.py`
  - `services/api/routers/control.py`
  - `services/api/routers/ops.py`
  - package exports in `services/api/__init__.py` and `services/api/routers/__init__.py`
- 2026-02-14: Updated dependency manifest:
  - `pyproject.toml` (`fastapi`, `httpx`)
  - `uv.lock` via `uv sync --all-groups`
- 2026-02-14: Updated docs and task tracking:
  - `README.md`
  - `.env.example`
  - `services/api/AGENT.md`
  - `docs/real_execution_go_baseline.md`
  - `docs/IMPLEMENTATION_PLAN.md`
  - continuous-learning notes in `docs/learning/2026-02-14-p7-control-plane-api-instincts.md`
- 2026-02-14: Verification complete:
  - `uv run pytest tests/test_p7_api_control_plane.py tests/test_p7_api_trading_ops.py tests/test_p7_api_docs.py -q`
  - `uv run pytest -q`
  - `uv run ruff check .`
  - `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`
