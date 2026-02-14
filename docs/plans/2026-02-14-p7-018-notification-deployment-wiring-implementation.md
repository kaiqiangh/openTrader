# Phase 7 Notification Deployment + Config Wiring (P7-018) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make notification stack deployable with validated startup config, compose wiring, and documented secrets/runtime instructions.

**Architecture:** Add a typed notification worker settings layer plus runtime worker entrypoint that can validate configuration and consume queue messages through pluggable consumers. Extend env/compose contracts and update docs to reflect operational startup paths.

**Tech Stack:** Python 3.13, Docker Compose, pytest, ruff.

---

### Task 1: Add failing deployment/config tests

**Files:**
- Create: `tests/test_p7_notification_deployment.py`
- Modify: `tests/test_p7_api_docs.py`

**Step 1: Write failing tests**

- Notification settings validation for enabled Telegram mode.
- Worker consume/process cycle via in-memory backend.
- Compose includes notification worker wiring.
- Docs gate requires `P7-018` completion.

**Step 2: Run tests to verify failures**

Run: `uv run pytest tests/test_p7_notification_deployment.py tests/test_p7_api_docs.py -q`  
Expected: FAIL before implementation/docs updates.

### Task 2: Implement settings + worker startup validation

**Files:**
- Create: `services/notification_service/settings.py`
- Create: `services/notification_service/worker.py`
- Modify: `services/notification_service/__init__.py`

### Task 3: Wire env/compose contracts

**Files:**
- Modify: `.env.example`
- Modify: `scripts/validate_env.py`
- Modify: `docker-compose.yml`

### Task 4: Update docs and plan tracking

**Files:**
- Modify: `README.md`
- Modify: `services/notification_service/AGENT.md`
- Modify: `services/workers/AGENT.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

### Task 5: Continuous learning record

**Files:**
- Create: `docs/learning/2026-02-14-p7-notification-deployment-instincts.md`

### Task 6: Verification

Run:

- `uv run pytest tests/test_p7_notification_deployment.py tests/test_p7_api_docs.py -q`
- `uv run pytest -q`
- `uv run ruff check .`
- `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`

Expected: PASS.

---

## Execution Log

- 2026-02-14: Plan created.
- 2026-02-14: Design recorded in `docs/plans/2026-02-14-p7-018-notification-deployment-wiring-design.md`.
- 2026-02-14: Added failing-first deployment tests for settings validation, worker processing, and compose/env contract assertions.
- 2026-02-14: Implemented notification worker settings loader, worker entrypoint, in-memory and RabbitMQ HTTP consumers, and startup validation CLI path.
- 2026-02-14: Wired `.env.example`, `scripts/validate_env.py`, `docker-compose.yml`, and README/deployment docs for notification worker runtime.
- 2026-02-14: Closed severity classification gap for `notify.risk.*` envelopes and marked `P7-018` as DONE in `docs/IMPLEMENTATION_PLAN.md`.
