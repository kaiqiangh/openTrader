# Phase 10 Runtime Status + Validation Stabilization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stabilize Phase 10 runtime infra behavior so compose smoke passes and update Phase 10 task statuses in the implementation plan using validated evidence.

**Architecture:** Harden the Go real-execution runtime loop to tolerate transient broker/API readiness races, align host-side smoke checks with compose networking, and then reclassify Phase 10 tasks based on runnable runtime validation evidence. Keep runtime worker/adapter contracts unchanged unless needed for boot reliability.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, RabbitMQ HTTP API, Go 1.21 service runner, Docker Compose, pytest, ruff, go test.

---

### Task 1: Reproduce runtime blocker and lock failing signal

**Files:**
- Read: `scripts/smoke_test.py`
- Read: `services/real_execution_go/internal/service/runner.go`
- Read: `services/real_execution_go/internal/consumer/rabbitmq_http.go`
- Read: `docker-compose.yml`

**Step 1: Execute current smoke gate**

Run: `make smoke`
Expected: FAIL because `real_execution_go` is not stable/running.

**Step 2: Capture supporting runtime logs**

Run: `docker compose ps`
Run: `docker compose logs --tail=120 real_execution_go rabbitmq`
Expected: observe consumer startup race/transient broker HTTP errors causing service restart.

### Task 2: Add resilient Go consumer-runner behavior

**Files:**
- Modify: `services/real_execution_go/internal/service/runner.go`
- Test: `services/real_execution_go/internal/service/runner_test.go`

**Step 1: Write failing/updated test case for consumer transient errors**
- Add test that consumer returns a non-`ErrNoMessage` error first, then no-message, and runner remains alive until context cancel.

**Step 2: Implement minimal recovery behavior**
- Change runner consumer-error branch to record failure metrics and continue loop with bounded backoff instead of hard exit.

**Step 3: Run Go unit tests**

Run: `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`
Expected: PASS.

### Task 3: Harden RabbitMQ HTTP consumer edge handling

**Files:**
- Modify: `services/real_execution_go/internal/consumer/rabbitmq_http.go`
- Test: `services/real_execution_go/internal/consumer/rabbitmq_http_test.go`

**Step 1: Add test for generic 404/object-not-found response mapping to no-message**

**Step 2: Implement handling**
- Treat all 404 queue fetch responses as `ErrNoMessage`.
- Add request header to avoid compressed 404 path instability (if applicable).

**Step 3: Run Go unit tests**

Run: `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`
Expected: PASS.

### Task 4: Align compose + smoke host connectivity

**Files:**
- Modify: `docker-compose.yml`
- Modify: `scripts/smoke_test.py`
- Test: `tests/test_smoke_script.py`

**Step 1: Ensure host-reachable RabbitMQ management for smoke checks**
- Map RabbitMQ management port in compose for local smoke checks.

**Step 2: Normalize smoke RabbitMQ API resolution**
- Resolve `RUNTIME_RABBITMQ_HTTP_API_URL` container hostnames (`rabbitmq`) to host equivalent (`127.0.0.1`) when running host-side probe.

**Step 3: Update/add smoke tests**

Run: `uv run pytest tests/test_smoke_script.py -q`
Expected: PASS.

### Task 5: Revalidate and update Phase 10 task status table

**Files:**
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Create: `docs/learning/2026-02-15-p10-runtime-status-validation-instincts.md`

**Step 1: Run target validation gates**

Run: `uv run pytest tests/test_p10_runtime_worker_entrypoints.py tests/test_runtime_persistence_adapters.py tests/test_p10_api_execution_bridge.py tests/test_smoke_script.py -q`
Run: `uv run ruff check ...`
Run: `make smoke`

**Step 2: Update Phase 10 statuses**
- Set each `P10-00X` status based on current evidence (done/in-progress/not-started).
- Update task tracking board % values.
- Append current turn update block and ledger row.
- Update immediate next actions for `P10-005/P10-006` transition.

**Step 3: Record learning notes**
- Add atomic instincts from this runtime hardening cycle.
