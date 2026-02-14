# Phase 7 Notification Delivery Hardening (P7-013 to P7-015) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver concrete Telegram notifications, operator preference APIs, and resilient anti-spam/retry behavior for notification delivery.

**Architecture:** Keep the provider abstraction in `notification_service` while introducing a concrete Telegram gateway implementation. Extend FastAPI control-plane with preference CRUD that maps to notification runtime preferences. Harden dispatcher and policy router logic with deterministic retry/backoff and suppression handling.

**Tech Stack:** Python 3.13, FastAPI, pytest, ruff.

---

### Task 1: Add failing tests for P7-013..P7-015

**Files:**
- Create: `tests/test_p7_notification_telegram_gateway.py`
- Create: `tests/test_p7_api_notification_preferences.py`
- Modify: `tests/test_p7_notification_service.py`
- Modify: `tests/test_p7_api_docs.py`

**Step 1: Write failing tests**

- Telegram sender/template tests:
  - markdown-safe template rendering.
  - retryable vs terminal error mapping.
- Preference API tests:
  - list/upsert/delete behavior.
  - validation and RBAC.
- Notification service tests:
  - retry backoff behavior.
  - rate-limit and dedupe suppression counters.

**Step 2: Run tests to verify failures**

Run: `uv run pytest tests/test_p7_notification_telegram_gateway.py tests/test_p7_api_notification_preferences.py tests/test_p7_notification_service.py tests/test_p7_api_docs.py -q`  
Expected: FAIL before implementation.

### Task 2: Implement Telegram gateway (`P7-013`)

**Files:**
- Create: `services/notification_service/telegram_gateway.py`
- Modify: `services/notification_service/gateway_dispatch.py`
- Modify: `services/notification_service/__init__.py`

**Step 1: Telegram gateway contracts**

- Add config dataclass and error type with retryability.
- Add template renderer with MarkdownV2 escaping.

**Step 2: Delivery behavior**

- Implement async gateway send path with injectable sender for tests.
- Map HTTP/network outcomes into retryable/terminal responses.

### Task 3: Implement preference management APIs (`P7-014`)

**Files:**
- Modify: `services/api/models.py`
- Modify: `services/api/state.py`
- Modify: `services/api/routers/ops.py`

**Step 1: API models and state records**

- Add preference request/response models.
- Add control-plane state CRUD for notification preferences.

**Step 2: API endpoints**

- Add list/upsert/delete notification preference endpoints.
- Enforce RBAC and payload validation.

### Task 4: Harden spam control + retry policy (`P7-015`)

**Files:**
- Modify: `services/notification_service/policy_router.py`
- Modify: `services/notification_service/gateway_dispatch.py`

**Step 1: Policy router hardening**

- Add suppression accounting for dedupe/rate-limit decisions.

**Step 2: Dispatcher retry hardening**

- Add bounded exponential backoff and retryable-only retries.
- Keep DLQ behavior explicit for terminal and exhausted retry failures.

### Task 5: Documentation and plan updates

**Files:**
- Modify: `README.md`
- Modify: `services/notification_service/AGENT.md`
- Modify: `services/api/AGENT.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

**Step 1: Docs**

- Document Telegram gateway and preference API surfaces.
- Document retry/backoff and suppression behavior.

**Step 2: Plan tracking**

- Mark `P7-013`, `P7-014`, `P7-015` done.
- Append progress ledger row and turn update.
- Advance immediate next actions.

### Task 6: Continuous learning record

**Files:**
- Create: `docs/learning/2026-02-14-p7-notification-delivery-instincts.md`

### Task 7: Verification

Run:

- `uv run pytest tests/test_p7_notification_telegram_gateway.py tests/test_p7_api_notification_preferences.py tests/test_p7_notification_service.py tests/test_p7_api_docs.py -q`
- `uv run pytest -q`
- `uv run ruff check .`
- `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`

Expected: PASS.

---

## Execution Log

- 2026-02-14: Plan created.
- 2026-02-14: Design recorded in `docs/plans/2026-02-14-p7-013-p7-015-notification-hardening-design.md`.
- 2026-02-14: Added failing tests for Telegram gateway behavior, notification preference APIs, and retry/backoff hardening.
- 2026-02-14: Implemented `services/notification_service/telegram_gateway.py` with MarkdownV2-safe template rendering and HTTP outcome mapping.
- 2026-02-14: Extended notification dispatcher with bounded exponential backoff and retryable/terminal delivery handling.
- 2026-02-14: Extended policy router with suppression counters for dedupe and rate-limit paths.
- 2026-02-14: Added notification preference CRUD contracts in API models/state and `/ops/notifications/preferences*` endpoints with RBAC.
- 2026-02-14: Updated docs (`README.md`, API/notification AGENT docs, `.env.example`, `IMPLEMENTATION_PLAN.md`).
- 2026-02-14: Targeted verification passed:
  - `uv run pytest tests/test_p7_notification_telegram_gateway.py tests/test_p7_api_notification_preferences.py tests/test_p7_notification_service.py tests/test_p7_api_docs.py -q`
- 2026-02-14: Full regression verification passed:
  - `uv run pytest -q`
  - `uv run ruff check .`
  - `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`
