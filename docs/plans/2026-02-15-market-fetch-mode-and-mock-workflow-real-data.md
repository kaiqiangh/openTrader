# Market Fetch Mode + Real-Data Mock Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add runtime-selectable market ingestion mode (REST vs websocket, default REST with 5-minute cadence), make mock realtime workflow publish real exchange/news data while keeping mock execution, and document frontend/dashboard startup.

**Architecture:** Extend the ingestion adapter with explicit delta-source selection and wire runtime worker construction to concrete exchange HTTP adapters for Binance/Bitget. Introduce polling cadence controls in worker runner for deterministic low-noise REST testing. Update the mock workflow script to fetch real market/news payloads for publish probes while preserving `execution.intent.mock` routing and strict LiteLLM validation.

**Tech Stack:** Python 3.13, asyncio, urllib, FastAPI dashboard shell docs, pytest.

---

### Task 1: Add fetch-mode contracts and exchange adapters

**Files:**
- Modify: `services/market_ingestion/exchange_adapter.py`
- Create: `services/market_ingestion/bitget_http_adapter.py`
- Modify: `services/market_ingestion/__init__.py`
- Test: `tests/test_p2_ingestion_adapter.py`
- Test: `tests/test_bitget_http_adapter.py`

**Step 1: Write failing tests**
- Add tests for REST delta-source behavior in `CCXTIngestionAdapter`.
- Add tests for Bitget HTTP payload normalization.

**Step 2: Run targeted tests (expect fail first)**
Run: `uv run pytest tests/test_p2_ingestion_adapter.py tests/test_bitget_http_adapter.py -q`

**Step 3: Implement minimal code**
- Add `delta_source` field (`rest`/`websocket`) to adapter and route `poll_delta` accordingly.
- Implement Bitget public orderbook HTTP client and normalized payload mapping.

**Step 4: Re-run tests (expect pass)**
Run: `uv run pytest tests/test_p2_ingestion_adapter.py tests/test_bitget_http_adapter.py -q`

### Task 2: Wire runtime worker fetch mode + cadence

**Files:**
- Modify: `services/workers/main.py`
- Modify: `.env.example`
- Test: `tests/test_p10_runtime_worker_entrypoints.py`

**Step 1: Write failing tests**
- Assert market worker chooses REST mode defaults and honors polling interval configuration.

**Step 2: Run targeted tests (expect fail first)**
Run: `uv run pytest tests/test_p10_runtime_worker_entrypoints.py -q`

**Step 3: Implement minimal code**
- Add env contracts for fetch mode and REST polling interval.
- Build runtime market adapter from concrete Binance/Bitget HTTP clients.
- Enforce minimum cycle interval in market runner for REST polling.

**Step 4: Re-run tests (expect pass)**
Run: `uv run pytest tests/test_p10_runtime_worker_entrypoints.py -q`

### Task 3: Make mock realtime workflow publish real market/news data

**Files:**
- Modify: `scripts/mock_realtime_workflow_test.py`
- Test: `tests/test_mock_realtime_workflow_script.py`

**Step 1: Write/adjust tests**
- Keep script-contract test assertions and add checks for real-fetch helper references.

**Step 2: Run targeted tests**
Run: `uv run pytest tests/test_mock_realtime_workflow_script.py -q`

**Step 3: Implement minimal code**
- Add `.env` loading at script startup.
- Replace hardcoded market payload with live Binance/Bitget REST fetch.
- Add live news fetch/parse pipeline for event payload enrichment.
- Keep mock execution path unchanged and preserve `--require-litellm` strict behavior.

**Step 4: Re-run tests**
Run: `uv run pytest tests/test_mock_realtime_workflow_script.py -q`

### Task 4: Documentation updates

**Files:**
- Modify: `README.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Create: `docs/learning/2026-02-15-market-fetch-mode-and-real-data-workflow-instincts.md`

**Step 1: Update README**
- Add frontend/dashboard startup and open instructions.
- Add new market fetch mode env notes with default REST polling.

**Step 2: Update implementation plan**
- Append current turn status ledger entry and turn update block.
- Capture follow-up work for websocket client hardening if needed.

**Step 3: Add learning note**
- Record atomic instincts learned from runtime fetch-mode and real-data workflow integration.

**Step 4: Validation sweep**
Run:
- `uv run ruff check services/market_ingestion services/workers scripts tests`
- `uv run pytest tests/test_p2_ingestion_adapter.py tests/test_bitget_http_adapter.py tests/test_p10_runtime_worker_entrypoints.py tests/test_mock_realtime_workflow_script.py -q`

