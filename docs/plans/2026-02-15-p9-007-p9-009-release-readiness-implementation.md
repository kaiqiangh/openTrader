# P9-007 to P9-009 Release Readiness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete Phase 9 closeout by delivering executable data-integrity and security acceptance gates plus a production-ready release/cutover package.

**Architecture:** Build deterministic acceptance tests on top of existing market-ingestion and security modules, then codify release/cutover workflows in auditable docs. Keep changes focused on validation and operational readiness artifacts without introducing new runtime complexity.

**Tech Stack:** Python 3.13, pytest, FastAPI TestClient, existing ingestion/security modules, markdown operational docs.

---

### Task 1: Implement `P9-007` data integrity audits

**Files:**
- Create: `tests/test_p9_data_integrity_audits.py`

**Step 1: Write failing tests**

- Add tests for:
  - sequence gap detection and resync request context,
  - order-book sync gap fault + snapshot-reload recovery,
  - kline reconstruction fault detection for missing intervals and interval mismatch.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p9_data_integrity_audits.py -q`
Expected: FAIL before implementation.

**Step 3: Write minimal implementation**

- Implement deterministic fixtures and assertions in test-only code.
- Reuse `GapDetectionModule`, `OrderBookSyncEngine`, `KlineReconstructionValidator`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p9_data_integrity_audits.py -q`
Expected: PASS.

### Task 2: Implement `P9-008` security acceptance suite

**Files:**
- Create: `tests/test_p9_security_acceptance.py`

**Step 1: Write failing tests**

- Add tests for:
  - RBAC enforcement (viewer denied for privileged mode switch),
  - encrypted secret at-rest behavior with decrypt round-trip,
  - network exposure boundaries in compose config,
  - notification secret placeholder rejection in settings.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p9_security_acceptance.py -q`
Expected: FAIL before implementation.

**Step 3: Write minimal implementation**

- Implement test harness and config assertions using current modules only.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p9_security_acceptance.py -q`
Expected: PASS.

### Task 3: Implement `P9-009` release checklist + cutover package docs

**Files:**
- Create: `docs/release/p9-release-checklist-2026-02-15.md`
- Create: `docs/release/p9-cutover-and-rollback-2026-02-15.md`

**Step 1: Write docs assertions first**

- Extend validation docs test to require new release docs and README references.

**Step 2: Run doc test to verify it fails**

Run: `uv run pytest tests/test_p9_validation_docs.py -q`
Expected: FAIL before docs update.

**Step 3: Write minimal implementation**

- Add checklist and cutover/rollback runbook with explicit verification gates.

**Step 4: Run doc test to verify it passes**

Run: `uv run pytest tests/test_p9_validation_docs.py -q`
Expected: PASS.

### Task 4: Phase 9 closure updates

**Files:**
- Modify: `tests/test_p9_validation_docs.py`
- Modify: `README.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Create: `docs/learning/2026-02-15-p9-007-p9-009-instincts.md`
- Create: `docs/runtime/p9-data-integrity-audit-2026-02-15.md`
- Create: `docs/runtime/p9-security-acceptance-2026-02-15.md`

**Step 1: Update validation and evidence docs**

- Record executed commands and outcomes for data-integrity and security acceptance gates.

**Step 2: Update implementation plan**

- Mark `P9-007..P9-009` as `DONE`.
- Append new progress ledger row and turn update.
- Update task board and immediate next actions.

**Step 3: Final verification**

Run:
- `uv run pytest tests/test_p9_data_integrity_audits.py tests/test_p9_security_acceptance.py tests/test_p9_validation_docs.py -q`
- `uv run pytest -q`
- `uv run ruff check .`

Expected: PASS.
