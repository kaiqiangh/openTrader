# P9 Validation Gates Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement and verify `P9-001`, `P9-002`, and `P9-003` with deterministic end-to-end validation tests and documentation updates.

**Architecture:** Reuse existing runtime workers and in-memory broker to validate end-to-end behavior without adding unnecessary runtime complexity. Compose OMS reconciliation/position/snapshot engines within tests to prove pipeline continuity from intent generation to portfolio-state outputs. Keep REAL-path validation contract-safe via emulated execution outcomes and reconciliation fallback checks.

**Tech Stack:** Python 3.13, pytest/pytest-asyncio, existing `services/*` runtime modules, markdown docs.

---

### Task 1: Implement `P9-001` E2E MOCK flow test

**Files:**
- Create: `tests/test_p9_e2e_mock_flow.py`

**Step 1: Write the failing test**

- Add an async test that runs:
  - market ingestion worker,
  - orchestrator runtime worker,
  - simulation execution worker,
  - reconciliation + position + portfolio snapshot composition.
- Assert full flow produces:
  - `execution.intent.mock`,
  - OMS lifecycle events,
  - reconciled filled order,
  - updated position and portfolio snapshot.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p9_e2e_mock_flow.py -q`
Expected: FAIL before implementation.

**Step 3: Write minimal implementation**

- Add scripted market clients and helper mappers inside the test file.
- Compose existing service modules only; avoid production code changes unless required.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p9_e2e_mock_flow.py -q`
Expected: PASS.

### Task 2: Implement `P9-002` E2E REAL flow validation test

**Files:**
- Create: `tests/test_p9_e2e_real_flow.py`

**Step 1: Write the failing test**

- Add async test for:
  - `market -> agent -> execution.intent.real` generation,
  - real-intent contract validation,
  - emulated lifecycle + exchange snapshot fallback reconciliation,
  - resulting position and portfolio snapshot assertions.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p9_e2e_real_flow.py -q`
Expected: FAIL before implementation.

**Step 3: Write minimal implementation**

- Add deterministic REAL test harness helper logic in test file only.
- Reuse `FillReconciliationEngine`, `PositionEngine`, and `PortfolioSnapshotEngine`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p9_e2e_real_flow.py -q`
Expected: PASS.

### Task 3: Implement `P9-003` mode isolation verification

**Files:**
- Create: `tests/test_p9_mode_isolation.py`

**Step 1: Write the failing test**

- Add async integration test with tracked exchange clients that expose order-write methods.
- Run full MOCK pipeline and assert:
  - no order-write methods were called,
  - no `execution.intent.real` messages emitted,
  - mock intent and OMS updates are produced as expected.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p9_mode_isolation.py -q`
Expected: FAIL before implementation.

**Step 3: Write minimal implementation**

- Implement tracked exchange client test doubles and assertions.
- Keep checks deterministic and independent of external services.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p9_mode_isolation.py -q`
Expected: PASS.

### Task 4: Documentation + plan status updates

**Files:**
- Create: `tests/test_p9_validation_docs.py`
- Create: `docs/runtime/p9-validation-2026-02-14.md`
- Modify: `README.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Create: `docs/learning/2026-02-14-p9-validation-instincts.md`

**Step 1: Write the failing doc test**

- Assert P9 validation files exist and `IMPLEMENTATION_PLAN.md` marks `P9-001..P9-003` as `DONE`.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p9_validation_docs.py -q`
Expected: FAIL before docs updates.

**Step 3: Write minimal implementation**

- Add runtime evidence doc and README references.
- Update implementation plan turn log, statuses, task board, and next actions.
- Capture learning notes for future validation phases.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p9_validation_docs.py -q`
Expected: PASS.

### Task 5: Validation run

**Files:**
- No source changes expected.

**Step 1: Run targeted P9 suite**

Run: `uv run pytest tests/test_p9_e2e_mock_flow.py tests/test_p9_e2e_real_flow.py tests/test_p9_mode_isolation.py tests/test_p9_validation_docs.py -q`
Expected: PASS.

**Step 2: Run full Python suite**

Run: `uv run pytest -q`
Expected: PASS.

**Step 3: Run lint**

Run: `uv run ruff check .`
Expected: PASS.

## Execution Log (2026-02-14)

- Plan created before implementation.
- Implementation to proceed test-first for each P9 gate.
