# Phase 10 Runtime Hardening (P10-003, P10-005, P10-006) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete Phase 10 runtime persistence and startup hardening by removing remaining in-memory runtime state on critical worker paths, removing startup-time `uv sync` from runtime service commands, and formalizing a dedicated runtime integration gate.

**Architecture:** Extend runtime worker persistence so market runtime cycles persist canonical orderbook snapshots via SQLAlchemy-backed stores, keep broker/runtime flows infrastructure-backed, and shift compose runtime startup to deterministic prebuilt Python runtime images. Add a dedicated runtime gate script/target that runs smoke + targeted runtime validations and emits a machine-readable report.

**Tech Stack:** Python 3.13, SQLAlchemy, FastAPI, RabbitMQ HTTP API, Docker Compose, Go runtime service, pytest, ruff, make.

---

### Task 1: Add market runtime persistence slice (P10-003)

**Files:**
- Modify: `services/workers/runtime_persistence.py`
- Modify: `services/workers/runtime_pipeline.py`
- Modify: `services/workers/main.py`
- Modify: `tests/test_p10_runtime_worker_entrypoints.py`
- Modify: `tests/test_runtime_persistence_adapters.py`

**Step 1: Write/extend failing tests**
- Add test to assert market worker with `runtime_engine` persists orderbook snapshots.
- Add adapter-level test for runtime market store transformation from canonical envelope to DB row.

**Step 2: Implement minimal persistence store**
- Add SQLAlchemy-backed market runtime store in `runtime_persistence.py` using `SQLAlchemyTimeseriesStore`.
- Convert canonical orderbook envelope payload into orderbook snapshot row (best bid/ask + spread_bps).

**Step 3: Wire runtime market worker to persistence**
- Extend `MarketIngestionRuntimeWorker` to accept optional market store and persist on each cycle.
- Inject market store from `build_runtime_worker` when runtime DB engine is present.

**Step 4: Validate tests**
Run: `uv run pytest tests/test_p10_runtime_worker_entrypoints.py tests/test_runtime_persistence_adapters.py -q`
Expected: PASS.

### Task 2: Remove startup-time `uv sync` from runtime start path (P10-005 hardening)

**Files:**
- Create: `docker/runtime-python.Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `scripts/smoke_test.py` (if needed for build behavior)

**Step 1: Add deterministic Python runtime image**
- Build dependencies at image build time with `uv sync --frozen --all-groups`.
- Keep runtime command as `uv run --frozen ...` (no startup sync in compose service commands).

**Step 2: Update runtime compose services**
- Replace per-service command prefixes `uv sync --all-groups && ...` with deterministic run commands.
- Keep health/dependency behavior intact.

**Step 3: Validate compose startup behavior**
Run: `docker compose up -d --build`
Run: `docker compose ps`
Expected: runtime services start without startup-time sync commands.

### Task 3: Formalize dedicated runtime integration gate (P10-006)

**Files:**
- Create: `scripts/runtime_integration_gate.py`
- Modify: `Makefile`
- Create: `tests/test_runtime_integration_gate.py`

**Step 1: Add gate runner script**
- Execute smoke + targeted runtime tests + Go tests.
- Emit JSON report artifact (e.g., `artifacts/runtime_integration_gate/latest.json`) including pass/fail, timestamp, and executed checks.

**Step 2: Expose make target**
- Add `runtime-gate` target invoking the gate script.

**Step 3: Add minimal tests**
- Verify script exists and make target wiring.

**Step 4: Validate**
Run: `uv run pytest tests/test_runtime_integration_gate.py tests/test_smoke_script.py -q`
Expected: PASS.

### Task 4: Update implementation + learning docs

**Files:**
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Create: `docs/learning/2026-02-15-p10-runtime-hardening-instincts.md`

**Step 1: Update plan status board**
- Recompute `P10-003/P10-005/P10-006` statuses and percentages from actual validation evidence.
- Append Turn Update block and ledger row.

**Step 2: Record continuous-learning instincts**
- Capture runtime persistence and startup determinism learnings.

**Step 3: Final verification**
Run:
- `uv run ruff check scripts/runtime_integration_gate.py scripts/smoke_test.py tests/test_runtime_integration_gate.py tests/test_smoke_script.py services/workers/main.py services/workers/runtime_pipeline.py services/workers/runtime_persistence.py`
- `uv run pytest tests/test_p10_runtime_worker_entrypoints.py tests/test_runtime_persistence_adapters.py tests/test_runtime_integration_gate.py tests/test_smoke_script.py -q`
- `make runtime-gate`
Expected: PASS with generated runtime gate report.

## Execution Update (2026-02-15)

- Task 1: completed; market runtime worker now persists canonical orderbook envelopes through `SQLAlchemyRuntimeMarketStore`.
- Task 2: completed; compose runtime commands now use `uv run --frozen` with dependency resolution moved to image build.
- Task 3: completed; dedicated `runtime-gate` runner emits `artifacts/runtime_integration_gate/latest.json` and now passes end-to-end.
- Task 4: completed for this slice; `IMPLEMENTATION_PLAN.md` and learning notes were updated with gate evidence, strategy lifecycle topology routing fix, and remaining `P10-003/P10-007` follow-ups.
