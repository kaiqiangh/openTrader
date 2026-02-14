# Phase 6 News Runtime Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete `P6-005`, `P6-006`, and `P6-007` with runnable context bridge, resilience fallback/alerting, and quality metrics contracts.

**Architecture:** Keep responsibilities split across three modules: context publication/injection (`context_injection_bridge.py`), resilience decisioning + alerts (`resilience.py`), and quality telemetry snapshots (`quality_metrics.py`). Validate via focused tests and then full-suite checks.

**Tech Stack:** Python 3.13, dataclasses, protocol-based boundaries, pytest, ruff.

---

### Task 1: P6-005 context injection bridge

**Files:**
- Create: `services/news_summarizer/context_injection_bridge.py`
- Create: `tests/test_p6_context_injection_bridge.py`
- Modify: `services/news_summarizer/__init__.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_context_bridge_publishes_summary_envelope_to_strategy_context_queue() -> None:
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p6_context_injection_bridge.py -v`
Expected: FAIL while module/contracts are missing.

**Step 3: Write minimal implementation**

- Add `NewsContextInjectionBridge` with:
  - `publish_summary_context(...)` envelope-validated publisher.
  - `inject_into_market_payload(...)` helper for market payload enrichment.
- Export bridge contracts from package `__init__.py`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p6_context_injection_bridge.py -v`
Expected: PASS.

### Task 2: P6-006 resilience behavior

**Files:**
- Create: `services/news_summarizer/resilience.py`
- Create: `tests/test_p6_news_resilience.py`
- Modify: `services/news_summarizer/__init__.py`

**Step 1: Write the failing test**

```python
def test_resilience_returns_fallback_and_alert_when_summary_missing() -> None:
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p6_news_resilience.py -v`
Expected: FAIL while module/contracts are missing.

**Step 3: Write minimal implementation**

- Add `NewsResiliencePolicy` with:
  - `evaluate(...)` handling missing/stale/fresh summary cases.
  - deterministic fallback payload `news_unavailable`.
  - `publish_alerts(...)` envelope-validated alert publisher.
- Export resilience contracts in package `__init__.py`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p6_news_resilience.py -v`
Expected: PASS.

### Task 3: P6-007 quality metrics

**Files:**
- Create: `services/news_ingestion/quality_metrics.py`
- Create: `tests/test_p6_quality_metrics.py`
- Modify: `services/news_ingestion/__init__.py`

**Step 1: Write the failing test**

```python
def test_quality_metrics_snapshot_exposes_coverage_freshness_lag_and_error_rate() -> None:
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p6_quality_metrics.py -v`
Expected: FAIL while module/contracts are missing.

**Step 3: Write minimal implementation**

- Add `NewsQualityMetrics` collector:
  - connector cycle counters
  - ingestion inserted/duplicate counters
  - summary lag tracking
  - quality snapshot output fields.
- Export `NewsQualityMetrics` from package `__init__.py`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p6_quality_metrics.py -v`
Expected: PASS.

### Task 4: Documentation and plan synchronization

**Files:**
- Modify: `README.md`
- Modify: `services/news_ingestion/AGENT.md`
- Modify: `services/news_summarizer/AGENT.md`
- Modify: `docs/agent_runtime_baseline.md`
- Modify: `docs/real_execution_go_baseline.md`
- Modify: `tests/test_p6_connector_docs.py`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

**Step 1: Extend docs tests**

Run: `uv run pytest tests/test_p6_connector_docs.py -v`
Expected: FAIL until new files/status updates are documented.

**Step 2: Update docs and plan tracking**

- Add module references for `P6-005..P6-007`.
- Mark `P6-005..P6-007` as `DONE` in phase table and live task board.
- Append progress ledger + turn update and move immediate next actions to Phase 7.

**Step 3: Re-run docs tests**

Run: `uv run pytest tests/test_p6_connector_docs.py -v`
Expected: PASS.

### Task 5: Full verification

**Files:**
- No additional file changes.

**Step 1: Run complete test/lint/go verification**

Run:
- `uv run pytest -q`
- `uv run ruff check .`
- `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`

Expected: PASS.

---

## Execution Log

- 2026-02-14: Plan created.
- 2026-02-14: Design recorded in `docs/plans/2026-02-14-p6-005-p6-007-news-context-quality-design.md`.
- 2026-02-14: Added failing tests for context bridge, resilience policy, and quality metrics.
- 2026-02-14: Implemented:
  - `services/news_summarizer/context_injection_bridge.py`
  - `services/news_summarizer/resilience.py`
  - `services/news_ingestion/quality_metrics.py`
- 2026-02-14: Updated package exports and documentation alignment.
- 2026-02-14: Verification complete:
  - `uv run pytest tests/test_p6_context_injection_bridge.py tests/test_p6_news_resilience.py tests/test_p6_quality_metrics.py tests/test_p6_connector_docs.py -q`
  - `uv run pytest -q`
  - `uv run ruff check .`
  - `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`
- 2026-02-14: `docs/IMPLEMENTATION_PLAN.md` updated with `P6-005..P6-007` set to `DONE` and next actions moved to `P7-001..P7-003`.
