# Phase 8 Observability Baseline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement structured logging, Prometheus-style metrics exposure, and trace-context propagation baseline for API, notification worker, and Go real-execution runtime.

**Architecture:** Introduce shared observability helpers in `services/shared/runtime` and integrate them incrementally into runtime entrypoints. Keep instrumentation additive and deterministic so existing behavior remains stable while exposing standardized logs/metrics/traces.

**Tech Stack:** Python 3.13, FastAPI, Go, pytest, go test, ruff.

---

### Task 1: Add failing tests for observability baseline

**Files:**
- Create: `tests/test_p8_observability_baseline.py`
- Modify: `tests/test_p7_api_control_plane.py`
- Modify: `services/real_execution_go/internal/metrics/collector_test.go`
- Create: `services/real_execution_go/internal/tracing/tracecontext_test.go`

**Step 1: Write failing tests**

- Assert structured logger emits JSON with required correlation keys.
- Assert API `/metrics` endpoint exists and exposes request metrics.
- Assert API request/response trace headers are propagated.
- Assert Go trace-context parser/build helper works.
- Assert Go runner metrics spans carry trace/decision IDs.

**Step 2: Run targeted tests to confirm failures**

Run:
- `uv run pytest tests/test_p8_observability_baseline.py tests/test_p7_api_control_plane.py -q`
- `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`

Expected: FAIL before implementation.

### Task 2: Implement shared Python observability utilities

**Files:**
- Create: `services/shared/runtime/structured_logging.py`
- Create: `services/shared/runtime/prometheus.py`
- Create: `services/shared/runtime/trace_context.py`
- Modify: `services/shared/runtime/__init__.py`

### Task 3: Integrate API middleware + `/metrics` endpoint

**Files:**
- Modify: `services/api/app.py`
- Modify: `services/api/routers/system.py`

### Task 4: Integrate notification worker structured logs/metrics/traces

**Files:**
- Modify: `services/notification_service/worker.py`

### Task 5: Add Go trace context and metric span propagation

**Files:**
- Create: `services/real_execution_go/internal/tracing/tracecontext.go`
- Modify: `services/real_execution_go/internal/metrics/collector.go`
- Modify: `services/real_execution_go/internal/service/runner.go`

### Task 6: Docs and plan updates

**Files:**
- Modify: `README.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Create: `docs/learning/2026-02-14-p8-observability-baseline-instincts.md`

### Task 7: Verification

Run:
- `uv run pytest tests/test_p8_observability_baseline.py tests/test_p7_api_control_plane.py -q`
- `uv run pytest -q`
- `uv run ruff check .`
- `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`

Expected: PASS.

---

## Execution Log

- 2026-02-14: Plan created.
- 2026-02-14: Design recorded in `docs/plans/2026-02-14-p8-observability-baseline-design.md`.
- 2026-02-14: Added failing tests for structured logs, API metrics/trace headers, docs gate checks, and Go trace-context behavior.
- 2026-02-14: Implemented shared observability runtime helpers (`structured_logging`, `prometheus`, `trace_context`) and wired FastAPI middleware with `/metrics`.
- 2026-02-14: Integrated notification worker structured logging and worker-level metrics instrumentation.
- 2026-02-14: Added Go trace-context helper package and propagated trace/decision IDs into runner telemetry spans.
- 2026-02-14: Updated README and implementation plan statuses for `P8-001..P8-003`.
