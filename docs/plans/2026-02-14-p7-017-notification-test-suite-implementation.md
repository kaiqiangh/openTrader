# Phase 7 Notification Test Suite Expansion (P7-017) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expand notification validation coverage with fault-injection scenarios and publish->deliver integration flow tests.

**Architecture:** Keep production behavior unchanged unless tests expose defects. Add focused pytest coverage around dispatcher retry semantics and cross-module integration from notification source bridge to delivery service and observability counters.

**Tech Stack:** Python 3.13, pytest, ruff.

---

### Task 1: Add failing tests for fault injection and integration flow

**Files:**
- Create: `tests/test_p7_notification_fault_injection.py`
- Create: `tests/test_p7_notification_integration_flow.py`
- Modify: `tests/test_p7_api_docs.py`

**Step 1: Write failing tests**

- Terminal exception path should skip retry loop and move to DLQ.
- Retryable failure exhaustion should respect bounded delay sequence and DLQ.
- Bridge publish output should be processable by `NotificationService` and delivered.

**Step 2: Run tests to verify failures**

Run: `uv run pytest tests/test_p7_notification_fault_injection.py tests/test_p7_notification_integration_flow.py tests/test_p7_api_docs.py -q`  
Expected: FAIL before plan/doc updates.

### Task 2: Fix any runtime gaps uncovered by tests

**Files:**
- Modify (if needed): `services/notification_service/gateway_dispatch.py`
- Modify (if needed): `services/notification_service/service.py`

### Task 3: Update docs + implementation plan tracking

**Files:**
- Modify: `README.md`
- Modify: `services/notification_service/AGENT.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

**Step 1: docs updates**

- Reflect that fault-injection and integration coverage are part of notification validation baseline.

**Step 2: plan tracking**

- Mark `P7-017` done.
- Append progress ledger row and turn update.
- Move next actions to `P7-018` and next observability/security steps.

### Task 4: Continuous learning note

**Files:**
- Create: `docs/learning/2026-02-14-p7-notification-testing-instincts.md`

### Task 5: Verification

Run:

- `uv run pytest tests/test_p7_notification_fault_injection.py tests/test_p7_notification_integration_flow.py tests/test_p7_notification_service.py tests/test_p7_notification_publishers.py tests/test_p7_api_docs.py -q`
- `uv run pytest -q`
- `uv run ruff check .`
- `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`

Expected: PASS.

---

## Execution Log

- 2026-02-14: Plan created.
- 2026-02-14: Design recorded in `docs/plans/2026-02-14-p7-017-notification-test-suite-design.md`.
- 2026-02-14: Added new fault-injection tests in `tests/test_p7_notification_fault_injection.py`.
- 2026-02-14: Added publish->deliver integration test in `tests/test_p7_notification_integration_flow.py`.
- 2026-02-14: Extended docs-gate assertion to require `P7-017` completion in `tests/test_p7_api_docs.py`.
- 2026-02-14: Updated README/AGENT/IMPLEMENTATION_PLAN documentation for notification validation baseline.
- 2026-02-14: Verification passed:
  - `uv run pytest tests/test_p7_notification_fault_injection.py tests/test_p7_notification_integration_flow.py tests/test_p7_notification_service.py tests/test_p7_notification_publishers.py tests/test_p7_api_docs.py -q`
  - `uv run pytest -q`
  - `uv run ruff check .`
  - `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`
