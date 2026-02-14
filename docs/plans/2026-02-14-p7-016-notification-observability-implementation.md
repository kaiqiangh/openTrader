# Phase 7 Notification Observability (P7-016) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add notification runtime telemetry (metrics/logs/traces) and expose it through API/dashboard hooks for operators.

**Architecture:** Introduce an in-process notification observability collector and connect it to `NotificationService` processing stages. Surface telemetry through `ops` endpoints and a dedicated dashboard view. Keep contracts deterministic and in-memory, deferring external exporters to Phase 8.

**Tech Stack:** Python 3.13, FastAPI, React 18 ESM static module, pytest, ruff.

---

### Task 1: Add failing tests for observability runtime and API/UI hooks

**Files:**
- Create: `tests/test_p7_notification_observability.py`
- Create: `tests/test_p7_api_notification_observability.py`
- Modify: `tests/test_p7_api_dashboard_ui.py`
- Modify: `tests/test_p7_api_docs.py`

**Step 1: Write failing tests**

- Runtime collector captures counters/logs/spans.
- `NotificationService` updates observability on processing path.
- API endpoints expose metrics/delivery logs/trace spans.
- Dashboard route includes `data-view='notifications'` and UI module references API paths.

**Step 2: Run tests to verify failures**

Run: `uv run pytest tests/test_p7_notification_observability.py tests/test_p7_api_notification_observability.py tests/test_p7_api_dashboard_ui.py tests/test_p7_api_docs.py -q`  
Expected: FAIL before implementation.

### Task 2: Implement notification observability runtime module

**Files:**
- Create: `services/notification_service/observability.py`
- Modify: `services/notification_service/models.py`
- Modify: `services/notification_service/service.py`
- Modify: `services/notification_service/__init__.py`

**Step 1: Collector model**

- Add in-memory collector with counters, recent structured logs, and recent trace spans.

**Step 2: Service integration**

- Inject collector in `NotificationService` and record intake/policy/dispatch phases.

### Task 3: Add API models/state/endpoints for notification telemetry

**Files:**
- Modify: `services/api/models.py`
- Modify: `services/api/state.py`
- Modify: `services/api/routers/ops.py`

**Step 1: API contracts**

- Add response schemas for metrics, delivery logs, and traces.

**Step 2: state + ops endpoints**

- Add in-memory telemetry snapshot/list helpers.
- Add read endpoints under `/ops/notifications/*`.

### Task 4: Add dashboard hooks

**Files:**
- Modify: `services/api/routers/dashboard.py`
- Modify: `services/api/static/dashboard_app.js`
- Modify: `services/api/static/dashboard.css`

**Step 1: route + nav**

- Add `/dashboard/notifications` shell route and nav item.

**Step 2: React notifications view**

- Fetch telemetry endpoints in parallel and render counters/log tables/trace table.

### Task 5: Documentation + implementation plan updates

**Files:**
- Modify: `README.md`
- Modify: `services/notification_service/AGENT.md`
- Modify: `services/api/AGENT.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

**Step 1: docs**

- Document notification observability module and API/dashboard surfaces.

**Step 2: plan tracking**

- Mark `P7-016` done.
- Append progress ledger row and turn update.
- Advance next actions.

### Task 6: Continuous learning record

**Files:**
- Create: `docs/learning/2026-02-14-p7-notification-observability-instincts.md`

### Task 7: Verification

Run:

- `uv run pytest tests/test_p7_notification_observability.py tests/test_p7_api_notification_observability.py tests/test_p7_api_dashboard_ui.py tests/test_p7_api_docs.py -q`
- `uv run pytest -q`
- `uv run ruff check .`
- `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`

Expected: PASS.

---

## Execution Log

- 2026-02-14: Plan created.
- 2026-02-14: Design recorded in `docs/plans/2026-02-14-p7-016-notification-observability-design.md`.
- 2026-02-14: Added failing tests for notification observability runtime collector, ops telemetry endpoints, and dashboard notification panel route/hook checks.
- 2026-02-14: Implemented `services/notification_service/observability.py` with counters, structured delivery logs, and trace spans.
- 2026-02-14: Integrated observability recording into `NotificationService` policy and dispatch stages.
- 2026-02-14: Added API telemetry contracts/state/endpoints for `/ops/notifications/metrics`, `/ops/notifications/deliveries`, and `/ops/notifications/traces`.
- 2026-02-14: Added `/dashboard/notifications` shell route and React `NotificationsView` with telemetry tables/cards.
- 2026-02-14: Updated docs (`README.md`, API/notification AGENT docs, `IMPLEMENTATION_PLAN.md`) and validated with targeted + full suites.
- 2026-02-14: Verification passed:
  - `uv run pytest tests/test_p7_notification_observability.py tests/test_p7_api_notification_observability.py tests/test_p7_api_dashboard_ui.py tests/test_p7_api_docs.py -q`
  - `uv run pytest -q`
  - `uv run ruff check .`
  - `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`
