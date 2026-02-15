# Runtime DB Policy Hardening + Doc-Test Stabilization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enforce Postgres/Timescale-first runtime database policy while preserving SQLite for deterministic local tests, and stabilize implementation-plan formatting contracts.

**Architecture:** Introduce a shared runtime DB settings/engine layer under `services/shared/runtime` and keep service-level adapters backend-agnostic through SQLAlchemy bind support.

**Tech Stack:** Python 3.13, SQLAlchemy, pytest, ruff.

---

### Task 1: Add shared runtime DB layer

**Files:**
- Create: `services/shared/runtime/database.py`
- Modify: `services/shared/runtime/__init__.py`
- Modify: `services/shared/runtime/sqlalchemy_utils.py`
- Test: `tests/test_shared_runtime_database.py`

**Steps:**
1. Write tests for Postgres URL composition, SQLite runtime rejection by default, and explicit SQLite test override.
2. Implement runtime DB settings + engine factory helpers.
3. Export new runtime DB layer from shared runtime package.
4. Run targeted tests then full suite.

### Task 2: Fix implementation-plan doc contract regressions

**Files:**
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Test: `tests/test_p5_oms_docs.py`, `tests/test_p6_connector_docs.py`, `tests/test_p7_api_docs.py`, `tests/test_p8_observability_docs.py`, `tests/test_p9_validation_docs.py`

**Steps:**
1. Restore status cell formatting expected by regex contract tests.
2. Preserve required P9 immediate-next-actions lines.
3. Run targeted doc tests and verify pass.

### Task 3: Update documentation and learning records

**Files:**
- Modify: `README.md`
- Create: `docs/learning/2026-02-15-runtime-db-policy-instincts.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

**Steps:**
1. Document runtime DB policy and env controls (`DATABASE_URL`, `ALLOW_SQLITE_RUNTIME`, pool settings).
2. Append progress ledger + turn update entries.
3. Record learning instincts and follow-up actions for `P10-003`.
