# Phase 7 Dashboard UI Layer (P7-007 to P7-009) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver governance dashboard UI, replay prompt/response inspector UI, and trading mode panel UI on top of FastAPI control-plane APIs.

**Architecture:** Serve a lightweight React module and stylesheet via FastAPI static files. Dashboard routes render HTML shells with per-view markers; React app fetches authenticated APIs and renders view-specific UI panels. Add a mode-history API for audit-facing mode panel requirements.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, React 18 ESM module, pytest, ruff.

---

### Task 1: Add failing tests for new UI and mode-audit behavior

**Files:**
- Modify: `tests/test_p7_api_control_plane.py`
- Create: `tests/test_p7_api_dashboard_ui.py`

**Step 1: Write failing tests**

- Add control-plane test for `GET /control/mode/history`.
- Add dashboard shell test asserting React shell markers/scripts for governance/replay/mode pages.

**Step 2: Run targeted tests to verify failures**

Run: `uv run pytest tests/test_p7_api_control_plane.py tests/test_p7_api_dashboard_ui.py -q`
Expected: FAIL before mode history endpoint and new dashboard shell support exist.

### Task 2: Implement mode-history API support

**Files:**
- Modify: `services/api/models.py`
- Modify: `services/api/state.py`
- Modify: `services/api/routers/control.py`

**Step 1: Add mode-audit response models**
- Add `ModeAuditRecordResponse` and `ModeHistoryResponse`.

**Step 2: Add mode-history state records**
- Persist mode transitions in `ControlPlaneState`.
- Expose list method with limit filtering.

**Step 3: Expose mode history endpoint**
- Add `GET /control/mode/history` guarded by `require_viewer`.

### Task 3: Implement dashboard UI shell + static React app

**Files:**
- Modify: `services/api/app.py`
- Modify: `services/api/routers/dashboard.py`
- Create: `services/api/static/dashboard_app.js`
- Create: `services/api/static/dashboard.css`

**Step 1: Static mounting**
- Mount `/static` assets from API service static directory.

**Step 2: Dashboard shell routes**
- Emit HTML shell with `data-view` marker for each page.
- Keep compatibility headings and navigation links.

**Step 3: React UI views**
- Governance view (`P7-007`): usage and breach tables with filters.
- Replay view (`P7-008`): replay request/decision lookup + prompt/response inspector.
- Mode view (`P7-009`): mode display/update + history table.

### Task 4: Update docs and plan tracking

**Files:**
- Modify: `README.md`
- Modify: `services/api/AGENT.md`
- Modify: `docs/real_execution_go_baseline.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Modify: `tests/test_p7_api_docs.py`

**Step 1: Update docs tests and references**
- Ensure new static UI files and tasks statuses are asserted.

**Step 2: Mark plan status**
- Mark `P7-007`, `P7-008`, `P7-009` as `DONE`.
- Add ledger row and turn update.
- Advance immediate next tasks.

### Task 5: Continuous learning log

**Files:**
- Create: `docs/learning/2026-02-14-p7-dashboard-ui-instincts.md`

**Step 1: Capture instincts**
- API-backed React shell pattern for FastAPI runtime.
- Parallel data fetching and derived-state rendering instincts.
- Mode-audit UI/API contract instinct.

### Task 6: Verification

Run:
- `uv run pytest tests/test_p7_api_control_plane.py tests/test_p7_api_dashboard_ui.py tests/test_p7_api_docs.py -q`
- `uv run pytest -q`
- `uv run ruff check .`
- `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`

Expected: PASS.

---

## Execution Log

- 2026-02-14: Plan created.
- 2026-02-14: Design recorded in `docs/plans/2026-02-14-p7-007-p7-009-dashboard-ui-design.md`.
- 2026-02-14: Added failing tests for mode history endpoint and dashboard React-shell/static-asset expectations.
- 2026-02-14: Implemented mode audit records in API state and exposed `GET /control/mode/history`.
- 2026-02-14: Reworked dashboard router into view-shell pages and mounted static React/CSS assets from FastAPI.
- 2026-02-14: Implemented governance/replay/mode React panels in `services/api/static/dashboard_app.js` and style system in `services/api/static/dashboard.css`.
- 2026-02-14: Updated docs/tests/plan tracking for `P7-007..P7-009` completion and next actions.
- 2026-02-14: Verification passed:
  - `uv run pytest tests/test_p7_api_control_plane.py tests/test_p7_api_dashboard_ui.py tests/test_p7_api_docs.py tests/test_p7_api_governance_replay_dashboard.py -q`
  - `uv run pytest -q`
  - `uv run ruff check .`
  - `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`
