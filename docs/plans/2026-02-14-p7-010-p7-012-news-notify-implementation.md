# Phase 7 News Panel + Notification Runtime (P7-010 to P7-012) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement news UI panel plus notification runtime core and source-pipeline event publisher integrations.

**Architecture:** Extend FastAPI control-plane APIs and dashboard React shell for news operations. Add a provider-agnostic notification service module with event intake, policy routing, gateway dispatch, and source bridge publishers. Integrate publisher hooks into strategy/OMS/risk/system-health producers.

**Tech Stack:** Python 3.13, FastAPI, React 18 ESM static module, pytest, ruff.

---

### Task 1: Add failing tests for P7-010..P7-012

**Files:**
- Create: `tests/test_p7_api_news_panel.py`
- Create: `tests/test_p7_notification_service.py`
- Create: `tests/test_p7_notification_publishers.py`
- Modify: `tests/test_p7_api_docs.py`

**Step 1: Write failing tests**

- News APIs + dashboard `/dashboard/news` shell checks.
- Notification runtime core behavior (severity mapping, dedupe/rate-limit, dispatch/DLQ).
- Source publisher integration tests for strategy/OMS/risk/system-health.

**Step 2: Run tests to verify failures**

Run: `uv run pytest tests/test_p7_api_news_panel.py tests/test_p7_notification_service.py tests/test_p7_notification_publishers.py tests/test_p7_api_docs.py -q`
Expected: FAIL before implementation.

### Task 2: Implement news panel backend + UI (`P7-010`)

**Files:**
- Modify: `services/api/models.py`
- Modify: `services/api/state.py`
- Modify: `services/api/routers/ops.py`
- Modify: `services/api/routers/dashboard.py`
- Modify: `services/api/static/dashboard_app.js`
- Modify: `services/api/static/dashboard.css`

**Step 1: API contracts and state**
- Add news response models.
- Add in-memory news state records and impact aggregation methods.

**Step 2: ops endpoints**
- Add `/ops/news/items`, `/ops/news/summaries`, `/ops/news/impact`.

**Step 3: dashboard news view**
- Add `/dashboard/news` shell route.
- Add React `NewsView` panel with parallel fetches and impact cards.

### Task 3: Implement notification service runtime core (`P7-011`)

**Files:**
- Create: `services/notification_service/__init__.py`
- Create: `services/notification_service/models.py`
- Create: `services/notification_service/event_intake.py`
- Create: `services/notification_service/policy_router.py`
- Create: `services/notification_service/gateway_dispatch.py`
- Create: `services/notification_service/service.py`
- Create: `services/notification_service/AGENT.md`

**Step 1: event intake**
- Normalize source envelope and map severity.

**Step 2: policy router**
- Preference filtering + dedupe/rate-limit enforcement.

**Step 3: gateway dispatch**
- Pluggable gateway contract and DLQ capture.

**Step 4: service orchestration**
- Implement process flow and return processing result.

### Task 4: Implement source event publisher integrations (`P7-012`)

**Files:**
- Create: `services/notification_service/publishers.py`
- Modify: `services/agent_orchestrator/orchestrator.py`
- Modify: `services/simulation_execution/worker.py`
- Modify: `services/oms/risk_observability.py`
- Modify: `services/workers/runtime_pipeline.py`

**Step 1: notification bridge publishers**
- Build normalized notification source events for strategy/OMS/risk/system incidents.

**Step 2: pipeline hooks**
- Hook orchestrator and simulation worker publisher callbacks.
- Capture risk notification envelopes from observability collector.
- Emit system-health notification envelope on runtime worker exception.

### Task 5: Update docs + implementation plan

**Files:**
- Modify: `README.md`
- Modify: `services/api/AGENT.md`
- Modify: `docs/real_execution_go_baseline.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

**Step 1: docs updates**
- Mention news panel APIs/UI and notification module/publishers.

**Step 2: plan tracking**
- Mark `P7-010`, `P7-011`, `P7-012` done.
- Add progress ledger row and turn update.
- Advance immediate next actions.

### Task 6: Continuous learning record

**Files:**
- Create: `docs/learning/2026-02-14-p7-news-notification-instincts.md`

### Task 7: Verification

Run:
- `uv run pytest tests/test_p7_api_news_panel.py tests/test_p7_notification_service.py tests/test_p7_notification_publishers.py tests/test_p7_api_docs.py -q`
- `uv run pytest -q`
- `uv run ruff check .`
- `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`

Expected: PASS.

---

## Execution Log

- 2026-02-14: Plan created.
- 2026-02-14: Design recorded in `docs/plans/2026-02-14-p7-010-p7-012-news-notify-design.md`.
- 2026-02-14: Added failing tests for news panel APIs/UI and notification runtime/publisher integrations.
- 2026-02-14: Implemented `P7-010` news panel data contracts, ops endpoints, dashboard route, and React `NewsView`.
- 2026-02-14: Implemented `P7-011` notification service core in `services/notification_service/` (`event_intake`, `policy_router`, `gateway_dispatch`, `service`).
- 2026-02-14: Implemented `P7-012` publisher bridge plus integration hooks in orchestrator, simulation worker, risk observability, and runtime worker health-failure path.
- 2026-02-14: Updated docs/tests/plan tracking and continuous-learning notes for the batch.
- 2026-02-14: Verification passed:
  - `uv run pytest tests/test_p7_api_news_panel.py tests/test_p7_notification_service.py tests/test_p7_notification_publishers.py tests/test_p7_api_docs.py -q`
  - `uv run pytest -q`
  - `uv run ruff check .`
  - `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`
