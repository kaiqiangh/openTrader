# Phase 8 Network Isolation + Security Suite + Runbooks Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete Phase 8 hardening by isolating compose networks, codifying security validation tests, and documenting operator incident runbooks.

**Architecture:** Harden deployment topology first, then enforce security invariants via deterministic tests, then finalize operational response documentation for core failure classes.

**Tech Stack:** Docker Compose, Python pytest, FastAPI auth contracts, Markdown runbooks.

---

### Task 1: Add failing tests for P8-007/P8-008/P8-009

**Files:**
- Create: `tests/test_p8_network_isolation.py`
- Create: `tests/test_p8_security_suite.py`
- Create: `tests/test_p8_runbooks.py`
- Modify: `tests/test_p8_observability_docs.py`

### Task 2: Implement compose network isolation hardening (`P8-007`)

**Files:**
- Modify: `docker-compose.yml`

### Task 3: Implement security suite coverage (`P8-008`)

**Files:**
- Create/Modify test files from Task 1 as needed

### Task 4: Implement runbooks (`P8-009`)

**Files:**
- Create: `docs/runbooks/AGENT.md`
- Create: `docs/runbooks/exchange-outage.md`
- Create: `docs/runbooks/llm-quota-breach.md`
- Create: `docs/runbooks/risk-incident.md`
- Modify: `README.md`

### Task 5: Update planning + learning docs

**Files:**
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Create: `docs/learning/2026-02-14-p8-007-p8-009-instincts.md`

### Task 6: Verification

Run:
- `uv run pytest tests/test_p8_network_isolation.py tests/test_p8_security_suite.py tests/test_p8_runbooks.py tests/test_p8_observability_docs.py -q`
- `uv run pytest -q`
- `uv run ruff check .`
- `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`

Expected: PASS.

---

## Execution Log

- 2026-02-14: Plan created.
- 2026-02-14: Design recorded in `docs/plans/2026-02-14-p8-007-p8-009-security-hardening-design.md`.
- 2026-02-14: Added failing-first tests for compose network isolation, consolidated security validations, runbook section coverage, and plan status gates.
- 2026-02-14: Hardened compose topology with `public` + `internal` networks and minimized host port exposure for internal services.
- 2026-02-14: Expanded Phase 8 security suite with JWT issuer/audience rejection checks and encrypted persistence assertions.
- 2026-02-14: Added operational runbooks for exchange outage, LLM quota breaches, and risk incidents with detection/containment/recovery workflows.
- 2026-02-14: Updated README and implementation plan tracking to complete `P8-007`, `P8-008`, and `P8-009`.
