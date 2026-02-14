# Notification System Docs + Phase 0-3 Gap Review + AGENT Files Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update architecture/planning docs for an extensible notification system, deliver a Phase 0-3 completeness gap report, and add consistent `AGENT.md` guidance files across core project directories.

**Architecture:** Extend PRD/ARD with notification requirements and gateway abstractions, then update implementation planning tasks for notification service delivery. Perform a codebase-backed review against Phase 0-3 claims and persist a structured severity-based report. Add root and nested `AGENT.md` files to codify boundaries, conventions, integration contracts, and testing expectations.

**Tech Stack:** Markdown documentation, repository structure conventions, existing planning artifacts.

---

### Task 1: Notification architecture document updates

**Files:**
- Modify: `docs/PRD_Consolidated.md`
- Modify: `docs/ARD_Consolidated.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

**Step 1: Write the failing test**

```python
def test_docs_define_extensible_notification_architecture() -> None:
    assert "Telegram" in prd and "gateway abstraction" in ard
```

**Step 2: Run test to verify it fails**

Run: `rg -n "notification|telegram|gateway" docs/PRD_Consolidated.md docs/ARD_Consolidated.md docs/IMPLEMENTATION_PLAN.md`
Expected: missing or incomplete notification architecture definitions.

**Step 3: Write minimal implementation**

- Add notification FRs/NFRs/preferences/severity/rate-limit/retry requirements in PRD.
- Add notification service/gateway/event-driven architecture and observability/scalability details in ARD.
- Add notification implementation tasks, config/deployment steps, and testing tasks in implementation plan.

**Step 4: Run test to verify it passes**

Run: `rg -n "notification|Telegram|gateway" docs/PRD_Consolidated.md docs/ARD_Consolidated.md docs/IMPLEMENTATION_PLAN.md`
Expected: all required sections present.

**Step 5: Commit**

```bash
git add docs/PRD_Consolidated.md docs/ARD_Consolidated.md docs/IMPLEMENTATION_PLAN.md
git commit -m "docs: add extensible notification architecture and implementation roadmap"
```

### Task 2: Phase 0-3 completeness gap analysis report

**Files:**
- Create: `docs/reviews/2026-02-14-phase0-3-gap-analysis.md`

**Step 1: Write the failing test**

```python
def test_gap_report_includes_severity_and_remediation() -> None:
    assert "Critical" in content and "Remediation Plan" in content
```

**Step 2: Run test to verify it fails**

Run: `test -f docs/reviews/2026-02-14-phase0-3-gap-analysis.md`
Expected: file does not exist.

**Step 3: Write minimal implementation**

- Cross-check implementation plan claims vs existing code/services/config/docs.
- Produce findings grouped by criticality and category.
- Add prioritized remediation and Phase 4 recommendations.

**Step 4: Run test to verify it passes**

Run: `rg -n "Critical|Important|Nice-to-have|Remediation|Phase 4" docs/reviews/2026-02-14-phase0-3-gap-analysis.md`
Expected: report sections present.

**Step 5: Commit**

```bash
git add docs/reviews/2026-02-14-phase0-3-gap-analysis.md
git commit -m "docs(review): add phase 0-3 completeness gap analysis"
```

### Task 3: Root and nested AGENT.md rollout

**Files:**
- Create: `AGENT.md`
- Create: `config/AGENT.md`
- Create: `services/AGENT.md`
- Create: `tests/AGENT.md`
- Create: `docs/AGENT.md`
- Create: `migrations/AGENT.md`
- Create: `scripts/AGENT.md`
- Create: service-level `AGENT.md` files for core service modules

**Step 1: Write the failing test**

```python
def test_agent_docs_exist_for_core_directories() -> None:
    assert Path("AGENT.md").exists()
    assert Path("services/AGENT.md").exists()
```

**Step 2: Run test to verify it fails**

Run: `rg --files | rg 'AGENT\.md$'`
Expected: missing files.

**Step 3: Write minimal implementation**

- Root `AGENT.md` with architecture principles, service interaction rules, observability/security/config standards, AI/LLM and notification gateway rules.
- Folder-level `AGENT.md` files documenting scope, boundaries, dependencies, extension/testing/operations conventions.
- Include nested template pattern in root file and apply style consistency.

**Step 4: Run test to verify it passes**

Run: `rg --files | rg 'AGENT\.md$'`
Expected: root + core nested AGENT docs present.

**Step 5: Commit**

```bash
git add AGENT.md config/AGENT.md services/AGENT.md tests/AGENT.md docs/AGENT.md migrations/AGENT.md scripts/AGENT.md
git commit -m "docs(agent): add root and module-level AGENT guidance"
```

## Execution Log (2026-02-14)

- Task 1 status: Completed.
- Task 2 status: Completed.
- Task 3 status: Completed.
- Notes:
  - Notification architecture updates were applied to PRD/ARD/implementation plan.
  - Phase 0-3 gap analysis report was added with severity-ranked findings and remediation plan.
  - Root and nested `AGENT.md` files were added for core directories and major service modules.
