# Phase 10 Runtime Cleanup + Doc Alignment (P10-003, P10-007) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Retire runtime-critical in-memory fallbacks on notification/ops paths, align runtime/docs for Compose bootstrap and integration gate operations, and add an end-to-end mocked realtime workflow validation script.

**Architecture:** Keep test/dev harness flexibility while enforcing infra-backed runtime defaults (RabbitMQ + Postgres/Timescale + Redis) for production startup paths. Consolidate integrity boundary decisions into explicit module ownership, and ensure operational docs match current worker/bootstrap behavior. Add a comprehensive smoke-style workflow script that validates mocked market/news/decision/execution/notification/database flow.

**Tech Stack:** Python 3.13, FastAPI, RabbitMQ HTTP API, SQLAlchemy, Docker Compose, pytest, Make, Markdown docs.

---

### Task 1: Runtime fallback policy hardening (`P10-003`)

**Files:**
- Modify: `services/notification_service/settings.py`
- Modify: `services/notification_service/worker.py`
- Modify: `services/api/app.py`
- Modify: `services/api/settings.py`
- Modify: `tests/test_notification_*` (as needed)
- Modify: `tests/test_p10_*` (as needed)

**Step 1: Write failing tests for runtime policy**
- Add tests asserting runtime settings reject in-memory notification backend unless explicitly test-enabled.
- Add tests asserting API can run in read-only runtime ops mode without write endpoints enabled.

**Step 2: Implement minimal policy enforcement**
- Add explicit runtime-mode guardrails for notification consumer backend selection.
- Add read-only ops guard for API write/control endpoints in runtime mode (config-driven).

**Step 3: Run focused tests**
- Run targeted pytest modules for notification + API policy behavior.

**Step 4: Validate runtime gate**
- Run `make runtime-gate` and ensure runtime policy changes keep full gate green.

### Task 2: Integrity service boundary decision and structure

**Files:**
- Modify/Create under: `services/integrity_service/`
- Modify: `services/market_ingestion/*` (imports/ownership if moved)
- Modify: `tests/test_p2_*`, `tests/test_repo_layout.py` (if needed)

**Step 1: Decide boundary**
- If integrity remains a dedicated bounded context, move/alias concrete integrity components into `services/integrity_service`.
- If not, remove boundary references from docs and service breakdown.

**Step 2: Implement minimal structural alignment**
- Add concrete module ownership in `services/integrity_service` (re-export or moved modules) and keep imports stable.

**Step 3: Validate**
- Run integrity-related tests and adjust docs references.

### Task 3: Compose/runtime error cleanup and determinism

**Files:**
- Modify: `docker-compose.yml`
- Modify: `scripts/smoke_test.py`
- Modify: `config/rabbitmq/topology.json` (if routing missing)
- Modify: `tests/test_smoke_script.py`, `tests/test_rabbitmq_topology.py`

**Step 1: Reproduce container errors**
- Use `docker compose up -d` + `docker compose ps` + logs to isolate restart causes.

**Step 2: Patch startup or routing gaps**
- Fix dependency/order/topology/service checks so all critical services remain running.

**Step 3: Validate**
- Run `make smoke` and `make runtime-gate`; verify all required services are stable.

### Task 4: Comprehensive mocked realtime workflow script

**Files:**
- Create: `scripts/mock_realtime_workflow_test.py`
- Modify: `Makefile` (add target)
- Create/Modify: `tests/test_mock_realtime_workflow_script.py`

**Step 1: Write failing script existence/contract tests**
- Assert script performs sequence checks for market/news/decision/execution/notification/db evidence.

**Step 2: Implement script**
- Validate compose services, bootstrap topology, publish mocked Binance/Bitget canonical events, publish mocked news events, verify decision intent + OMS event + notification log path + DB persistence evidence checks.

**Step 3: Validate**
- Run script locally and corresponding tests.

### Task 5: LiteLLM/DeepSeek runtime configuration alignment

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/ARD_Consolidated.md`
- Modify: `docs/PRD_Consolidated.md`

**Step 1: Document concrete DeepSeek-through-LiteLLM configuration**
- Add exact env examples and request flow.

**Step 2: Ensure code references are explicit**
- Add/align runtime setting references and docs so users can find where LiteLLM variables are consumed.

### Task 6: Plan and learning documentation update (`P10-007`)

**Files:**
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Create: `docs/learning/2026-02-15-p10-cleanup-doc-alignment-instincts.md`

**Step 1: Update turn ledger + Phase 10 statuses**
- Record completed/in-progress IDs and next actions from runtime evidence.

**Step 2: Record continuous-learning instincts**
- Capture root-cause patterns for runtime determinism, topology routing, and env clarity.

**Step 3: Final verification**
- `uv run ruff check ...` on changed Python/tests.
- `uv run pytest ...` on changed suites.
- `make smoke` and `make runtime-gate`.
