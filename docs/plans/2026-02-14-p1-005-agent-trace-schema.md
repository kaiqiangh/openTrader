# P1-005 Agent Trace Schema Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the `P1-005` database migration for agent decision trace persistence (`decision_traces`, `agent_runs`, `agent_messages`) with tests and documentation updates.

**Architecture:** Add one forward Alembic migration chained after `20260214_0002` that creates normalized trace tables with clear foreign keys and indexes for query paths (`decision_id`, `agent_run_id`, timestamp lookups). Keep schema minimal (YAGNI) but aligned to ARD so replay and governance features have stable persistence contracts.

**Tech Stack:** Python 3.13+, Alembic, SQLAlchemy, PostgreSQL + TimescaleDB repo baseline, pytest.

---

### Task 1: Add Failing Tests for Agent Trace Migration

**Files:**
- Create: `/Users/kai/Desktop/openTrader/tests/test_phase1_agent_trace_migration.py`
- Test: `/Users/kai/Desktop/openTrader/tests/test_phase1_agent_trace_migration.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_agent_trace_migration_exists() -> None:
    migration = Path("migrations/versions/20260214_0003_agent_trace_schema.py")
    assert migration.exists()


def test_agent_trace_migration_has_required_tables() -> None:
    content = Path("migrations/versions/20260214_0003_agent_trace_schema.py").read_text(encoding="utf-8")
    assert "decision_traces" in content
    assert "agent_runs" in content
    assert "agent_messages" in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_phase1_agent_trace_migration.py -v`
Expected: FAIL because migration file does not exist.

**Step 3: Write minimal implementation**

Create migration file with required table names and Alembic metadata.

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_phase1_agent_trace_migration.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/tests/test_phase1_agent_trace_migration.py /Users/kai/Desktop/openTrader/migrations/versions/20260214_0003_agent_trace_schema.py
git commit -m "feat(db): add agent trace schema migration"
```

### Task 2: Implement Agent Trace Migration Schema

**Files:**
- Create: `/Users/kai/Desktop/openTrader/migrations/versions/20260214_0003_agent_trace_schema.py`
- Test: `/Users/kai/Desktop/openTrader/tests/test_phase1_agent_trace_migration.py`

**Step 1: Write the failing test**

```python
def test_agent_trace_migration_has_fk_and_indexes() -> None:
    content = Path("migrations/versions/20260214_0003_agent_trace_schema.py").read_text(encoding="utf-8")
    assert "ForeignKey(\"decision_traces.decision_id\")" in content
    assert "ForeignKey(\"agent_runs.agent_run_id\")" in content
    assert "idx_agent_runs_decision_id" in content
    assert "idx_agent_messages_agent_run_id_created_at" in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_phase1_agent_trace_migration.py -v`
Expected: FAIL because FK/index strings are missing.

**Step 3: Write minimal implementation**

```python
op.create_table("decision_traces", ...)
op.create_table("agent_runs", ... ForeignKey("decision_traces.decision_id") ...)
op.create_table("agent_messages", ... ForeignKey("agent_runs.agent_run_id") ...)
op.create_index("idx_agent_runs_decision_id", ...)
op.create_index("idx_agent_messages_agent_run_id_created_at", ...)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_phase1_agent_trace_migration.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/migrations/versions/20260214_0003_agent_trace_schema.py /Users/kai/Desktop/openTrader/tests/test_phase1_agent_trace_migration.py
git commit -m "feat(db): add foreign keys and indexes for agent trace schema"
```

### Task 3: Update Project Documentation and Progress Tracking

**Files:**
- Modify: `/Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md`
- Modify: `/Users/kai/Desktop/openTrader/README.md`
- Test: `/Users/kai/Desktop/openTrader/tests/test_phase1_migrations.py`

**Step 1: Write the failing test**

```python
def test_readme_mentions_agent_trace_migration() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "20260214_0003_agent_trace_schema.py" in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_phase1_migrations.py -v`
Expected: FAIL if docs line missing.

**Step 3: Write minimal implementation**

- Add migration reference to `README.md`.
- Update `docs/IMPLEMENTATION_PLAN.md`:
  - Mark `P1-005` as `DONE`
  - Append turn update entry
  - Update immediate next actions.

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests -v`
Expected: PASS for full suite.

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/README.md /Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md /Users/kai/Desktop/openTrader/tests
git commit -m "docs: record P1-005 completion and update migration references"
```
