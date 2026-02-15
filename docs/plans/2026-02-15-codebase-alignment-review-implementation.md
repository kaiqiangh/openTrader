# Codebase Alignment Review + Strategic Documentation Refresh Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver an evidence-based architecture/product alignment review, publish remediation decisions, and update core docs (`README`, `PRD`, `ARD`, `IMPLEMENTATION_PLAN`) to match real runtime status.

**Architecture:** Use a doc-first audit workflow: map documented expectations to concrete code paths, classify gaps by severity, then codify approved decisions (DB, messaging, triggering, deployment) and a prioritized remediation backlog.

**Tech Stack:** Python 3.13, FastAPI, Go, RabbitMQ, PostgreSQL/TimescaleDB, Redis, Docker Compose, pytest, ruff.

---

### Task 1: Build Evidence Matrix

**Files:**
- Modify: `docs/plans/2026-02-15-codebase-alignment-review-implementation.md`
- Read: `docs/PRD_Consolidated.md`
- Read: `docs/ARD_Consolidated.md`
- Read: `docs/IMPLEMENTATION_PLAN.md`
- Read: `services/**`
- Read: `tests/**`

**Step 1: Write the failing test**

```python
def test_alignment_matrix_exists():
    assert False, "evidence matrix not built"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q`
Expected: FAIL (placeholder failure or missing matrix evidence in docs updates).

**Step 3: Write minimal implementation**

```python
# Replace placeholder with a concrete mapping:
# requirement -> implementation status -> file evidence -> severity.
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q`
Expected: PASS for existing suite with no new regressions.

**Step 5: Commit**

```bash
git add docs/plans/2026-02-15-codebase-alignment-review-implementation.md
git commit -m "docs: add codebase alignment review implementation plan"
```

### Task 2: Update Architecture and Product Source Documents

**Files:**
- Modify: `docs/ARD_Consolidated.md`
- Modify: `docs/PRD_Consolidated.md`

**Step 1: Write the failing test**

```python
def test_arch_docs_include_runtime_reality_section():
    assert "Current Implementation Reality" in open("docs/ARD_Consolidated.md").read()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q`
Expected: FAIL until sections are added.

**Step 3: Write minimal implementation**

```python
# Add explicit "current vs target" status sections and production decisions:
# - Timescale usage scope
# - RabbitMQ-only event boundaries
# - Hybrid trigger model
# - Compose full-stack requirement
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add docs/ARD_Consolidated.md docs/PRD_Consolidated.md
git commit -m "docs: align PRD and ARD with runtime reality and architecture decisions"
```

### Task 3: Update Implementation Plan With Remediation Backlog

**Files:**
- Modify: `docs/IMPLEMENTATION_PLAN.md`

**Step 1: Write the failing test**

```python
def test_phase10_remediation_exists():
    content = open("docs/IMPLEMENTATION_PLAN.md").read()
    assert "Phase 10" in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q`
Expected: FAIL until remediation phase is added.

**Step 3: Write minimal implementation**

```python
# Add new remediation phase with prioritized P10 tasks and current-turn update.
# Keep existing P5-P9 DONE records in expected table format for regression tests.
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add docs/IMPLEMENTATION_PLAN.md
git commit -m "docs: add phase-10 remediation backlog and turn update"
```

### Task 4: Upgrade Root README for Production Onboarding

**Files:**
- Modify: `README.md`

**Step 1: Write the failing test**

```python
def test_readme_has_api_endpoints_and_roadmap():
    content = open("README.md").read()
    assert "API Endpoints" in content
    assert "Roadmap" in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q`
Expected: FAIL until sections are added.

**Step 3: Write minimal implementation**

```python
# Add:
# - architecture diagram
# - service breakdown
# - event flow
# - docker runbook
# - env and Telegram setup
# - strategy extension guide
# - observability guide
# - contribution and roadmap
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add README.md
git commit -m "docs: upgrade README with architecture, operations, and roadmap"
```

