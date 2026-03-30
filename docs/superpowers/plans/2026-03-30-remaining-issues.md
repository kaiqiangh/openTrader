# Remaining Issues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

**Goal:** Fix all remaining issues from 3 rounds of code review

**Current state:** 722 tests passing, P0/P1/CQ/Tier 1-3 all resolved. Remaining: 18 issues (2 CRITICAL, 4 HIGH, 7 MEDIUM, 5 LOW).

---

## Tier A: CRITICAL (fix immediately)

### A-1: REQ-006 — Position Mode Isolation at Query Level

**Impact:** MOCK and REAL positions can leak into each other's portfolio calculations.

**Problem:** `positions` table now has `mode` column (migration 0010), but queries don't filter by mode. `list_positions()`, portfolio snapshot, and risk calculations pull all positions regardless of mode.

**Files:**
- `services/api/repositories.py` — position queries need `WHERE mode = :mode`
- `services/workers/runtime_persistence.py` — same
- `services/oms/portfolio_snapshot.py` — positions param should be mode-filtered
- `services/api/routers/ops.py` — endpoints should pass mode

**Steps:**
1. Add `mode` parameter to all position query functions
2. Add `WHERE mode = :mode` to SQL queries
3. Pass `mode` from control plane state through API endpoints
4. Write tests verifying MOCK positions don't appear in REAL queries
5. Commit

### A-2: REQ-016 — Dashboard Endpoints Auth (verify status)

**Impact:** Need to verify whether dashboard auth was actually applied.

**Problem:** Round 2 subagent reported "unauthenticated" but Round 4 check showed auth already present. Need to confirm.

**Steps:**
1. Read `services/api/routers/dashboard.py`
2. Verify all endpoints have `Depends(require_viewer)`
3. If already fixed, document and move on
4. If not fixed, add auth

---

## Tier B: HIGH (fix soon)

### B-1: REQ-004 — LLM Quota Soft Alerts (80%/95%)

**Impact:** No early warning before hitting LLM quota hard-stop.

**Files:**
- `services/llm_gateway/gateway.py` — quota enforcement
- `services/notification_service/` — emit warning events

**Steps:**
1. Find quota enforcement code
2. Add soft-threshold checks at 80% and 95%
3. Emit warning notifications via RabbitMQ
4. Write tests
5. Commit

### B-2: REQ-009 — Replay "Compare vs Original"

**Impact:** Replay reconstructs traces but doesn't re-execute agents to compare.

**Files:**
- `services/api/routers/replay.py` — replay endpoint
- `services/agent_orchestrator/` — re-execution

**Steps:**
1. Read replay service code
2. Add diff mode that re-runs agent prompts and compares output
3. Write tests
4. Commit

### B-3: LOGIC-013 — Health Server Thread-Safety

**Impact:** `healthy` flag is a data race between main thread and daemon HTTP thread.

**Files:**
- `services/workers/health.py`

**Steps:**
1. Replace bare `self.healthy` bool with `threading.Event`
2. Use `event.set()` / `event.clear()` / `event.is_set()`
3. Write test for concurrent access
4. Commit

### B-4: TEST-009 — Edge Case Test Density (2.9% → 20%)

**Impact:** Most tests are happy-path only. Edge cases untested.

**Steps:**
1. Audit existing tests for missing edge cases
2. Add boundary tests for: empty inputs, zero values, null/None, concurrent access
3. Focus on OMS, risk, and API routers
4. Commit

---

## Tier C: MEDIUM (fix in next session)

### C-1: LOGIC-014 — Health Port Env Var Conflicts

**Problem:** `WORKER_HEALTH_PORT` env var gives all workers the same port.

**Fix:** Use per-worker env vars like `WORKER_MARKET_HEALTH_PORT`.

### C-2: REQ-011 — Notification Metrics DB Persistence

**Problem:** Notification observability is in-memory only.

**Fix:** Persist delivery results to `notification_deliveries` table.

### C-3: REQ-015 — Celery Placeholder Tasks

**Problem:** All 5 Celery tasks return `{"status": "placeholder"}`.

**Fix:** Implement at least `data_retention_cleanup` (most critical).

### C-4: REQ-020 — Decimal/float Boundary in Risk Rules

**Problem:** `evaluate()` accepts `Decimal | float` but callers still pass float.

**Fix:** Update all callers to pass Decimal.

### C-5: SEC-029 — Docker Containers Run as Root

**Problem:** No `USER` directive in Dockerfiles.

**Fix:** Add non-root user to `docker/runtime-python.Dockerfile`.

### C-6: SEC-022 — PostgreSQL No TLS

**Problem:** No `sslmode=require` in connection strings.

**Fix:** Add SSL config for production deployments.

### C-7: SEC-030 — Broad CORS Headers

**Problem:** `allow_headers=["*"]`.

**Fix:** Restrict to `["Authorization", "Content-Type", "X-Request-ID"]`.

---

## Tier D: LOW (defer)

- SEC-037: .env.example placeholder passwords
- SEC-038: sync_publish silent failure
- REQ-019: PG TLS for local dev (acceptable)
- REQ-021: Celery profile configuration
- LOGIC-017: ccxt exception narrowing (already has logging)

---

## Execution Order

1. A-1 (mode isolation) — highest impact code change
2. A-2 (dashboard auth verify) — quick check
3. B-1 (quota alerts) — important monitoring gap
4. B-3 (health thread-safety) — small fix
5. B-4 (edge case tests) — coverage improvement
6. B-2 (replay diff) — larger feature
7. C-1 through C-7 — batch in one session
8. D items — defer unless time permits
