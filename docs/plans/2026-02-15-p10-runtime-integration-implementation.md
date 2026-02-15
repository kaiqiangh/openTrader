# Phase 10 Runtime Integration (P10-001 to P10-003) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver the first concrete Phase 10 runtime slice by adding worker entrypoint CLIs, RabbitMQ-backed runtime broker adapters, and Postgres-capable persistence adapters.

**Architecture:** Keep domain logic unchanged and add runtime boundary adapters in `services/shared/runtime` and `services/workers`. Use dependency injection for broker/store backends so tests can keep deterministic in-memory behavior while runtime can switch to RabbitMQ/Postgres through env configuration.

**Tech Stack:** Python 3.13, SQLAlchemy, psycopg, RabbitMQ HTTP API, pytest, ruff.

---

### Task 1: Add Runtime Worker Entrypoint Skeletons (P10-001)

**Files:**
- Create: `services/workers/main.py`
- Modify: `services/workers/__init__.py`
- Test: `tests/test_p10_runtime_worker_entrypoints.py`

**Step 1: Write the failing test**

```python
def test_worker_cli_parses_runtime_role():
    assert parse_args(["--worker", "orchestrator", "--once"]).worker == "orchestrator"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p10_runtime_worker_entrypoints.py -q`
Expected: FAIL (module/function not found).

**Step 3: Write minimal implementation**

```python
# services/workers/main.py
# - parse --worker / --once / --max-idle-cycles
# - wire runtime worker runners
# - return process exit code
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p10_runtime_worker_entrypoints.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add services/workers/main.py services/workers/__init__.py tests/test_p10_runtime_worker_entrypoints.py
git commit -m "feat(workers): add phase-10 runtime worker entrypoint CLI skeleton"
```

### Task 2: Add RabbitMQ HTTP Topic Broker Adapter (P10-002)

**Files:**
- Create: `services/shared/runtime/rabbitmq_http_broker.py`
- Modify: `services/shared/runtime/__init__.py`
- Modify: `services/workers/main.py`
- Test: `tests/test_p10_rabbitmq_http_broker.py`

**Step 1: Write the failing test**

```python
async def test_rabbitmq_http_broker_publish_uses_exchange_mapping():
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p10_rabbitmq_http_broker.py -q`
Expected: FAIL (adapter missing).

**Step 3: Write minimal implementation**

```python
# Add RabbitMQHTTPTopicBroker with:
# - publish(routing_key, message)
# - consume(queue_name, timeout_seconds)
# - optional queue declare/bootstrap for missing queues
# - topology-based routing_key -> exchange resolution
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p10_rabbitmq_http_broker.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add services/shared/runtime/rabbitmq_http_broker.py services/shared/runtime/__init__.py services/workers/main.py tests/test_p10_rabbitmq_http_broker.py
git commit -m "feat(runtime): add RabbitMQ HTTP topic broker adapter for phase-10 path"
```

### Task 3: Add Postgres-Capable SQLAlchemy Runtime Stores (P10-003)

**Files:**
- Modify: `services/market_ingestion/sqlalchemy_store.py`
- Modify: `services/agent_orchestrator/sqlalchemy_memory_store.py`
- Modify: `services/llm_gateway/sqlalchemy_stores.py`
- Test: `tests/test_runtime_persistence_adapters.py`

**Step 1: Write the failing test**

```python
def test_runtime_stores_accept_sqlalchemy_engine():
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runtime_persistence_adapters.py -q`
Expected: FAIL (stores only accept sqlite3 connection assumptions).

**Step 3: Write minimal implementation**

```python
# Store constructors accept SQLAlchemy Engine/Connection while preserving sqlite compatibility.
# Keep schema bootstrap behavior and current interfaces.
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_runtime_persistence_adapters.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add services/market_ingestion/sqlalchemy_store.py services/agent_orchestrator/sqlalchemy_memory_store.py services/llm_gateway/sqlalchemy_stores.py tests/test_runtime_persistence_adapters.py
git commit -m "feat(runtime): make phase-10 persistence stores sqlalchmey/postgres-capable"
```

### Task 4: Plan/Learning Documentation Sync

**Files:**
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Create: `docs/learning/2026-02-15-p10-runtime-integration-instincts.md`

**Step 1: Write the failing test**

```python
def test_implementation_plan_has_latest_turn_update():
    assert "Turn Update 2026-02-15" in Path("docs/IMPLEMENTATION_PLAN.md").read_text()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q`
Expected: FAIL or stale status before update.

**Step 3: Write minimal implementation**

```python
# Append turn update + progress ledger entry
# Add continuous-learning instincts for this P10 slice
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q && uv run ruff check .`
Expected: PASS.

**Step 5: Commit**

```bash
git add docs/IMPLEMENTATION_PLAN.md docs/learning/2026-02-15-p10-runtime-integration-instincts.md
git commit -m "docs: update phase-10 runtime integration progress and learning notes"
```

