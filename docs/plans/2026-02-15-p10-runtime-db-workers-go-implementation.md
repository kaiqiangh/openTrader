# Phase 10 Runtime DB Wiring + Worker Persistence + Go Integration Start Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the next Phase 10 runtime slice by enforcing DB fail-fast startup behavior, moving remaining in-memory worker runtime state to Postgres-backed stores, and starting concrete Go real-execution queue/bridge/publisher integration (`P10-004`).

**Architecture:** Keep service contracts stable and add infrastructure adapters behind explicit interfaces. Python runtime workers get a shared SQLAlchemy runtime DB boundary and persistent worker stores. Go real-execution replaces noop runtime wiring with concrete RabbitMQ HTTP consumer, HTTP bridge client, and OMS event publisher contracts.

**Tech Stack:** Python 3.13, SQLAlchemy, psycopg, FastAPI runtime modules, Go 1.21 stdlib HTTP, RabbitMQ HTTP API, pytest, ruff, go test.

---

### Task 1: Wire runtime DB fail-fast into worker startup

**Files:**
- Modify: `services/workers/main.py`
- Modify: `.env.example`
- Test: `tests/test_p10_runtime_worker_entrypoints.py`

**Step 1: Write the failing test**

```python
def test_runtime_worker_fails_when_db_policy_rejects_backend():
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p10_runtime_worker_entrypoints.py -q`
Expected: FAIL (no DB startup validation path).

**Step 3: Write minimal implementation**

```python
# Add runtime DB validation in startup path:
# - load shared DB settings/engine
# - execute SELECT 1
# - fail-fast on config/connectivity errors when runtime DB is required
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p10_runtime_worker_entrypoints.py -q`
Expected: PASS.

### Task 2: Replace remaining in-memory worker state with SQL-backed stores (P10-003 continuation)

**Files:**
- Create: `services/workers/runtime_persistence.py`
- Modify: `services/workers/main.py`
- Test: `tests/test_p10_runtime_worker_entrypoints.py`

**Step 1: Write the failing test**

```python
def test_oms_worker_persists_state_in_sql_store():
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p10_runtime_worker_entrypoints.py -q`
Expected: FAIL (worker uses in-memory dict stores).

**Step 3: Write minimal implementation**

```python
# Add SQLAlchemy-backed runtime stores:
# - OMS order/event/position/snapshot store
# - News item/tag/summary store
# Wire these stores into runtime worker builders when DB engine is present.
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p10_runtime_worker_entrypoints.py -q`
Expected: PASS.

### Task 3: Start P10-004 Go concrete runtime integration

**Files:**
- Modify: `services/real_execution_go/main.go`
- Create: `services/real_execution_go/internal/consumer/rabbitmq_http.go`
- Create: `services/real_execution_go/internal/bridge/http_client.go`
- Create: `services/real_execution_go/internal/publisher/contracts.go`
- Create: `services/real_execution_go/internal/publisher/rabbitmq_http.go`
- Modify: `services/real_execution_go/internal/service/handler.go`
- Test: `services/real_execution_go/internal/consumer/rabbitmq_http_test.go`
- Test: `services/real_execution_go/internal/bridge/http_client_test.go`
- Test: `services/real_execution_go/internal/service/handler_test.go`

**Step 1: Write the failing test**

```go
func TestRabbitMQHTTPConsumerReceive(t *testing.T) { ... }
func TestHTTPBridgeExecute(t *testing.T) { ... }
func TestHandlerPublishesSubmittedEvent(t *testing.T) { ... }
```

**Step 2: Run test to verify it fails**

Run: `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`
Expected: FAIL (concrete adapters/publisher not implemented).

**Step 3: Write minimal implementation**

```go
// Replace noop runtime wiring with:
// - concrete RabbitMQ HTTP consumer
// - concrete HTTP bridge client
// - OMS event publisher contract + RabbitMQ publisher implementation
// - handler publish hooks for submitted/rejected outcomes
```

**Step 4: Run test to verify it passes**

Run: `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`
Expected: PASS.

### Task 4: Update implementation/learning docs and validate full suite

**Files:**
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Create: `docs/learning/2026-02-15-p10-runtime-db-workers-go-instincts.md`
- Modify: `README.md`

**Step 1: Write the failing test**

```python
def test_plan_and_readme_reference_runtime_db_policy_and_p10_progress():
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q`
Expected: FAIL or stale docs before updates.

**Step 3: Write minimal implementation**

```python
# Append turn update + progress ledger row.
# Update P10 progress and immediate-next actions.
# Record continuous-learning instincts and runtime policy notes.
```

**Step 4: Run test to verify it passes**

Run:
- `uv run pytest -q`
- `uv run ruff check .`
- `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`

Expected: all PASS.

---

## Execution Notes (2026-02-15)

- Implemented runtime worker DB fail-fast startup validation in `/Users/kai/Desktop/openTrader/services/workers/main.py` via shared runtime DB layer (`SELECT 1` connectivity check).
- Added SQL-backed runtime worker stores in `/Users/kai/Desktop/openTrader/services/workers/runtime_persistence.py` and wired OMS/news workers to use these stores when runtime engine is available.
- Started `P10-004` concrete Go runtime integration:
  - `/Users/kai/Desktop/openTrader/services/real_execution_go/internal/consumer/rabbitmq_http.go`
  - `/Users/kai/Desktop/openTrader/services/real_execution_go/internal/bridge/http_client.go`
  - `/Users/kai/Desktop/openTrader/services/real_execution_go/internal/publisher/contracts.go`
  - `/Users/kai/Desktop/openTrader/services/real_execution_go/internal/publisher/rabbitmq_http.go`
  - `/Users/kai/Desktop/openTrader/services/real_execution_go/internal/service/handler.go`
  - `/Users/kai/Desktop/openTrader/services/real_execution_go/main.go`
- Validation completed:
  - `uv run pytest -q` PASS
  - `uv run ruff check .` PASS
  - `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...` PASS
