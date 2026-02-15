# P9-004 to P9-006 Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete `P9-004`, `P9-005`, and `P9-006` with deterministic replay, performance, and resilience validation suites plus runtime evidence docs.

**Architecture:** Reuse existing in-process runtime components to keep tests deterministic while still exercising real orchestration paths. Focus on contract-level reproducibility (replay), bounded latency/throughput telemetry (performance), and controlled fault injection with recovery assertions (chaos/resilience).

**Tech Stack:** Python 3.13, pytest/pytest-asyncio, FastAPI state/replay services, in-memory broker, markdown runtime docs.

---

### Task 1: Implement `P9-004` replay determinism validation

**Files:**
- Create: `tests/test_p9_replay_determinism.py`

**Step 1: Write the failing test**

- Add async tests that:
  - seed `ControlPlaneState` replay stores with intentionally unsorted agent runs/messages/LLM calls,
  - invoke replay twice and assert deterministic digest equality,
  - assert replay lifecycle reproduces the exact stored decision chain and ordering is canonicalized.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p9_replay_determinism.py -q`
Expected: FAIL before implementation.

**Step 3: Write minimal implementation**

- Implement deterministic fixture builders and assertions in the test file only.
- Reuse existing replay contracts (`DecisionTraceRecord`, `AgentRunRecord`, `AgentMessageRecord`, `LLMCallRecord`, `DecisionMemoryRecord`).

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p9_replay_determinism.py -q`
Expected: PASS.

### Task 2: Implement `P9-005` performance benchmark validation

**Files:**
- Create: `tests/test_p9_performance_benchmarks.py`

**Step 1: Write the failing test**

- Add tests that measure:
  - dispatch latency p95 from `SimulationExecutionWorker.run_once`,
  - broker queue throughput for publish+consume loops,
  - ingestion lag from canonical envelope `emitted_at` vs market `timestamp_ms`.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p9_performance_benchmarks.py -q`
Expected: FAIL before implementation.

**Step 3: Write minimal implementation**

- Add deterministic benchmark harness helpers in test-only fixtures.
- Keep thresholds realistic and non-flaky for CI.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p9_performance_benchmarks.py -q`
Expected: PASS.

### Task 3: Implement `P9-006` chaos/resilience drills

**Files:**
- Create: `tests/test_p9_chaos_resilience.py`

**Step 1: Write the failing test**

- Add drill tests for:
  - broker temporary outage then recovery,
  - exchange disconnect then reconnect with health notification,
  - LLM timeout on primary then fallback success,
  - long-term memory persist failure then retry success (DB restart analogue).

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p9_chaos_resilience.py -q`
Expected: FAIL before implementation.

**Step 3: Write minimal implementation**

- Implement fault-injection doubles and recovery assertions.
- Reuse existing runtime modules; avoid new production abstractions unless strictly required.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p9_chaos_resilience.py -q`
Expected: PASS.

### Task 4: Runtime evidence docs and plan updates

**Files:**
- Create: `docs/runtime/p9-replay-determinism-2026-02-15.md`
- Create: `docs/runtime/p9-performance-benchmark-2026-02-15.md`
- Create: `docs/runtime/p9-resilience-drills-2026-02-15.md`
- Create: `docs/learning/2026-02-15-p9-004-p9-006-instincts.md`
- Modify: `tests/test_p9_validation_docs.py`
- Modify: `README.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

**Step 1: Write failing doc assertions**

- Extend `tests/test_p9_validation_docs.py` to require new test files/docs and `P9-004..P9-006` statuses as `DONE`.

**Step 2: Run doc test to verify it fails**

Run: `uv run pytest tests/test_p9_validation_docs.py -q`
Expected: FAIL before docs/plan updates.

**Step 3: Write minimal implementation**

- Add runtime evidence docs with executed commands and outcomes.
- Update README references and implementation plan statuses/progress ledger/next actions.
- Add continuous-learning instincts doc for this phase increment.

**Step 4: Run doc test to verify it passes**

Run: `uv run pytest tests/test_p9_validation_docs.py -q`
Expected: PASS.

### Task 5: Final validation

**Files:**
- No source changes expected.

**Step 1: Run targeted Phase 9 suite**

Run: `uv run pytest tests/test_p9_replay_determinism.py tests/test_p9_performance_benchmarks.py tests/test_p9_chaos_resilience.py tests/test_p9_validation_docs.py -q`
Expected: PASS.

**Step 2: Run full Python suite**

Run: `uv run pytest -q`
Expected: PASS.

**Step 3: Run lint**

Run: `uv run ruff check .`
Expected: PASS.

## Execution Log (2026-02-15)

- Plan created before implementation.
- Implementation to proceed in deterministic test-first order per task.
