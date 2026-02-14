# Runtime Integration Gate + P4 Routing/Simulation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver a runnable Phase 2-3 runtime integration gate (broker/workers/adapters/persistence) and then implement `P4-001`, `P4-002`, and `P4-003` on top of that pipeline.

**Architecture:** Introduce a concrete in-process broker adapter and worker runtime wiring that can execute ingestion -> canonical publish -> orchestrator -> execution intent flow in deterministic tests. Add concrete persistence adapters for timeseries, memory, and LLM governance through SQLAlchemy repositories, plus a concrete LiteLLM-compatible HTTP client adapter. Then implement strict mode routing policy, simulation engine core, and simulation safety guard with regression tests.

**Tech Stack:** Python 3.13, SQLAlchemy, asyncio, stdlib HTTP (`urllib`), pytest.

---

### Task 1: Runtime integration gate foundations

**Files:**
- Create: `/Users/kai/Desktop/openTrader/services/shared/runtime/__init__.py`
- Create: `/Users/kai/Desktop/openTrader/services/shared/runtime/broker.py`
- Create: `/Users/kai/Desktop/openTrader/services/workers/runtime_pipeline.py`
- Test: `/Users/kai/Desktop/openTrader/tests/test_runtime_pipeline.py`

**Step 1: Write the failing test**

```python
async def test_runtime_pipeline_moves_market_event_to_execution_intent():
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runtime_pipeline.py -v`
Expected: FAIL because runtime broker/worker modules do not exist.

**Step 3: Write minimal implementation**

- Add in-memory broker adapter with publish/consume semantics.
- Add market ingestion worker and orchestrator worker using existing contracts.
- Add runtime coordinator helper to run one deterministic cycle.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_runtime_pipeline.py -v`
Expected: PASS with execution intent published to mode-specific queue.

**Step 5: Commit**

```bash
git add services/shared/runtime services/workers/runtime_pipeline.py tests/test_runtime_pipeline.py
git commit -m "feat(runtime): add in-process broker and worker pipeline runtime"
```

### Task 2: Concrete persistence and LLM provider adapters

**Files:**
- Create: `/Users/kai/Desktop/openTrader/services/shared/runtime/sqlalchemy_utils.py`
- Create: `/Users/kai/Desktop/openTrader/services/market_ingestion/sqlalchemy_store.py`
- Create: `/Users/kai/Desktop/openTrader/services/agent_orchestrator/sqlalchemy_memory_store.py`
- Create: `/Users/kai/Desktop/openTrader/services/llm_gateway/sqlalchemy_stores.py`
- Create: `/Users/kai/Desktop/openTrader/services/llm_gateway/litellm_http_adapter.py`
- Test: `/Users/kai/Desktop/openTrader/tests/test_runtime_persistence_adapters.py`
- Test: `/Users/kai/Desktop/openTrader/tests/test_litellm_http_adapter.py`

**Step 1: Write the failing test**

```python
def test_sqlalchemy_adapters_persist_and_load_records():
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runtime_persistence_adapters.py tests/test_litellm_http_adapter.py -v`
Expected: FAIL because adapter modules do not exist.

**Step 3: Write minimal implementation**

- Add SQLAlchemy repositories for timeseries writes, memory summary reads/writes, LLM call persistence, and quota usage.
- Add LiteLLM-compatible HTTP client adapter with timeout and response normalization.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_runtime_persistence_adapters.py tests/test_litellm_http_adapter.py -v`
Expected: PASS for adapter persistence and HTTP payload parsing.

**Step 5: Commit**

```bash
git add services/shared/runtime/sqlalchemy_utils.py services/market_ingestion/sqlalchemy_store.py services/agent_orchestrator/sqlalchemy_memory_store.py services/llm_gateway/sqlalchemy_stores.py services/llm_gateway/litellm_http_adapter.py tests/test_runtime_persistence_adapters.py tests/test_litellm_http_adapter.py
git commit -m "feat(runtime): add concrete persistence and LiteLLM HTTP adapters"
```

### Task 3: Implement P4-001, P4-002, P4-003

**Files:**
- Create: `/Users/kai/Desktop/openTrader/services/simulation_execution/mode_routing.py`
- Create: `/Users/kai/Desktop/openTrader/services/simulation_execution/engine.py`
- Create: `/Users/kai/Desktop/openTrader/services/simulation_execution/safety_guard.py`
- Create: `/Users/kai/Desktop/openTrader/services/simulation_execution/worker.py`
- Test: `/Users/kai/Desktop/openTrader/tests/test_p4_mode_routing.py`
- Test: `/Users/kai/Desktop/openTrader/tests/test_p4_simulation_engine.py`
- Test: `/Users/kai/Desktop/openTrader/tests/test_p4_simulation_safety_guard.py`

**Step 1: Write the failing test**

```python
def test_mode_router_rejects_invalid_mode_and_leakage():
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p4_mode_routing.py tests/test_p4_simulation_engine.py tests/test_p4_simulation_safety_guard.py -v`
Expected: FAIL because P4 modules do not exist.

**Step 3: Write minimal implementation**

- Add strict routing policy utility for mode-specific queues.
- Add deterministic simulation engine with slippage/fee application.
- Add safety guard that blocks real endpoint usage in MOCK mode.
- Add simulation worker that consumes mock intents and emits lifecycle events.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p4_mode_routing.py tests/test_p4_simulation_engine.py tests/test_p4_simulation_safety_guard.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add services/simulation_execution tests/test_p4_mode_routing.py tests/test_p4_simulation_engine.py tests/test_p4_simulation_safety_guard.py
git commit -m "feat(p4): add mode routing, simulation engine, and mock safety guard"
```

### Task 4: Plan/documentation alignment and validation gate updates

**Files:**
- Modify: `/Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md`
- Modify: `/Users/kai/Desktop/openTrader/docs/agent_runtime_baseline.md`
- Create: `/Users/kai/Desktop/openTrader/docs/runtime/runtime-integration-gate-2026-02-14.md`

**Step 1: Write the failing test**

```python
def test_implementation_plan_reflects_runtime_gate_before_p4():
    ...
```

**Step 2: Run test to verify it fails**

Run: `rg -n "Phase 3.5|runtime integration gate|P4-001" docs/IMPLEMENTATION_PLAN.md`
Expected: missing runtime gate framing.

**Step 3: Write minimal implementation**

- Add a runtime integration gate section and explicit Phase 4 entry criteria.
- Update turn ledger and task board statuses.
- Add runtime verification document for the new worker pipeline.

**Step 4: Run test to verify it passes**

Run: `rg -n "runtime integration gate|Phase 4 entry criteria|P4-001|P4-003" docs/IMPLEMENTATION_PLAN.md docs/runtime/runtime-integration-gate-2026-02-14.md`
Expected: required sections present.

**Step 5: Commit**

```bash
git add docs/IMPLEMENTATION_PLAN.md docs/agent_runtime_baseline.md docs/runtime/runtime-integration-gate-2026-02-14.md
git commit -m "docs: align plan with runtime integration gate and p4 execution criteria"
```

## Execution Log (2026-02-14)

- Task 1 status: Completed.
- Task 2 status: Completed.
- Task 3 status: Completed.
- Task 4 status: Completed.
- Notes:
  - User requested runtime integration gate completion before P4 delivery.
  - Plan enforces runnable pipeline proof before considering Phase 4 complete.
  - Runtime gate and P4 foundations were implemented with passing targeted tests.
  - Full repository pytest suite passed after integration (`167 passed`).
