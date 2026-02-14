# Phase 7 Governance + Replay + Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement `P7-004`, `P7-005`, and `P7-006` with governance APIs, replay APIs, and dashboard shell routes on the existing FastAPI control plane.

**Architecture:** Extend API surface with three routers (`governance`, `replay`, `dashboard`), typed response models, and control-plane state adapters for governance aggregates and replay reconstruction. Keep route handlers thin and delegate data composition to state/service helpers.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, pytest, ruff.

---

### Task 1: Add failing tests for governance/replay/dashboard endpoints

**Files:**
- Create: `tests/test_p7_api_governance_replay_dashboard.py`

**Step 1: Write failing tests**

```python
def test_governance_usage_and_breach_endpoints_return_expected_payloads() -> None:
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p7_api_governance_replay_dashboard.py -v`
Expected: FAIL because governance/replay/dashboard routes and models do not exist.

**Step 3: Implement minimal routes/state/models to satisfy tests**

- Add governance router endpoints.
- Add replay router endpoints.
- Add dashboard HTML shell endpoints.
- Add required state/model support.

**Step 4: Re-run targeted tests**

Run: `uv run pytest tests/test_p7_api_governance_replay_dashboard.py -v`
Expected: PASS.

### Task 2: Implement governance + replay + dashboard modules

**Files:**
- Modify: `services/api/app.py`
- Modify: `services/api/routers/__init__.py`
- Modify: `services/api/models.py`
- Modify: `services/api/state.py`
- Create: `services/api/routers/governance.py`
- Create: `services/api/routers/replay.py`
- Create: `services/api/routers/dashboard.py`

**Step 1: Governance endpoints (`P7-004`)**

- `GET /governance/llm/usage`
- `GET /governance/llm/breaches`

**Step 2: Replay endpoints (`P7-005`)**

- `POST /replay/requests`
- `GET /replay/requests/{request_id}`
- `GET /replay/decisions/{decision_id}`

**Step 3: Dashboard shell (`P7-006`)**

- `GET /dashboard`
- `GET /dashboard/status`
- `GET /dashboard/governance`
- `GET /dashboard/replay`

### Task 3: Update docs tests and documentation

**Files:**
- Modify: `tests/test_p7_api_docs.py`
- Modify: `README.md`
- Modify: `services/api/AGENT.md`
- Modify: `docs/real_execution_go_baseline.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

**Step 1: Extend docs tests for new modules and task statuses**

Run: `uv run pytest tests/test_p7_api_docs.py -v`
Expected: FAIL until docs and plan are updated.

**Step 2: Update docs and plan**

- Mention new API modules in README and AGENT docs.
- Mark `P7-004..P7-006` as `DONE` in implementation plan.
- Add progress ledger row + turn update and move next actions to `P7-007..P7-009`.

### Task 4: Continuous Learning v2 record

**Files:**
- Create: `docs/learning/2026-02-14-p7-governance-replay-dashboard-instincts.md`

**Step 1: Capture atomic instincts**

- Governance aggregation boundary instinct.
- Replay API contract + not-found semantics instinct.
- Dashboard shell composition instinct.

### Task 5: Full verification

Run:
- `uv run pytest -q`
- `uv run ruff check .`
- `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`

Expected: PASS.

---

## Execution Log

- 2026-02-14: Plan created.
- 2026-02-14: Design recorded in `docs/plans/2026-02-14-p7-004-p7-006-governance-replay-dashboard-design.md`.
- 2026-02-14: Implementation started in this session.
- 2026-02-14: Added failing-first contract test file `tests/test_p7_api_governance_replay_dashboard.py` and validated red->green cycle.
- 2026-02-14: Implemented `services/api/routers/governance.py`, `services/api/routers/replay.py`, `services/api/routers/dashboard.py` with app/router wiring updates.
- 2026-02-14: Extended `services/api/models.py` and `services/api/state.py` for governance aggregation and replay request/result support.
- 2026-02-14: Updated docs/tests (`README.md`, `services/api/AGENT.md`, `docs/real_execution_go_baseline.md`, `tests/test_p7_api_docs.py`, `docs/IMPLEMENTATION_PLAN.md`).
- 2026-02-14: Verification passed:
  - `uv run pytest tests/test_p7_api_governance_replay_dashboard.py tests/test_p7_api_docs.py -q`
  - `uv run pytest -q`
  - `uv run ruff check .`
  - `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`
