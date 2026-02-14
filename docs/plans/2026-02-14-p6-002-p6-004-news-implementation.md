# Phase 6 News Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver `P6-002`, `P6-003`, and `P6-004` with deterministic ingestion, tagging, and rolling summary generation modules.

**Architecture:** Build contract-first service modules around the existing connector framework. `ingestion_service.py` handles normalization/dedupe/persistence, `tagging_relevance.py` annotates items with symbol/topic/relevance/sentiment, and `summarizer_service.py` produces rolling summaries with explicit fallback behavior.

**Tech Stack:** Python 3.13, dataclasses, pytest, ruff.

---

### Task 1: Add failing tests for P6-002 ingestion and dedupe persistence

**Files:**

- Create: `tests/test_p6_ingestion_service.py`
- Create: `services/news_ingestion/ingestion_service.py`

**Step 1: Write failing tests**

```python
def test_news_ingestion_service_dedupes_by_source_item_and_hash() -> None:
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p6_ingestion_service.py -v`
Expected: FAIL because module does not exist.

**Step 3: Write minimal implementation**

- Add normalized item dataclass and ingest result dataclasses.
- Add `NewsItemStore` protocol and in-memory store for deterministic tests.
- Implement dedupe by `(source, source_item_id)` and by hash.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p6_ingestion_service.py -v`
Expected: PASS.

### Task 2: Add failing tests for P6-003 tagging/relevance pipeline

**Files:**

- Create: `tests/test_p6_tagging_relevance.py`
- Create: `services/news_ingestion/tagging_relevance.py`

**Step 1: Write failing tests**

```python
def test_tagging_pipeline_assigns_symbol_topic_relevance_sentiment() -> None:
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p6_tagging_relevance.py -v`
Expected: FAIL because module does not exist.

**Step 3: Write minimal implementation**

- Add tag dataclass and store protocol.
- Implement keyword-based symbol/topic detection and bounded scoring.
- Persist tags through store contract.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p6_tagging_relevance.py -v`
Expected: PASS.

### Task 3: Add failing tests for P6-004 rolling summarizer

**Files:**

- Create: `tests/test_p6_summarizer_service.py`
- Create: `services/news_summarizer/summarizer_service.py`
- Create: `services/news_summarizer/__init__.py`

**Step 1: Write failing tests**

```python
def test_news_summarizer_builds_windowed_scope_summary() -> None:
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p6_summarizer_service.py -v`
Expected: FAIL because module does not exist.

**Step 3: Write minimal implementation**

- Add summary artifact dataclass and store protocol.
- Implement deterministic rolling window summary text from tagged items.
- Add empty-window fallback summary (`news_unavailable`).

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p6_summarizer_service.py -v`
Expected: PASS.

### Task 4: Package exports and docs assertions

**Files:**

- Modify: `services/news_ingestion/__init__.py`
- Modify: `tests/test_p6_connector_docs.py`
- Modify: `README.md`
- Modify: `services/news_summarizer/AGENT.md`
- Modify: `docs/agent_runtime_baseline.md`

**Step 1: Extend docs tests**

Run: `uv run pytest tests/test_p6_connector_docs.py -v`
Expected: FAIL until docs mention new modules and status updates.

**Step 2: Update docs and exports**

- Add new module references.
- Keep docs aligned with actual runtime-ready boundaries.

**Step 3: Re-run docs tests**

Run: `uv run pytest tests/test_p6_connector_docs.py -v`
Expected: PASS.

### Task 5: Update implementation plan + verify all

**Files:**

- Modify: `docs/IMPLEMENTATION_PLAN.md`

**Step 1: Update statuses and turn protocol**

- Mark `P6-002`, `P6-003`, `P6-004` as `DONE`.
- Add progress ledger row and new turn update block.
- Update immediate next actions.

**Step 2: Run full verification**

Run:

- `uv run pytest -q`
- `uv run ruff check .`
- `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`

Expected: PASS.

---

## Execution Log

- 2026-02-14: Plan created.
- 2026-02-14: Design recorded in `docs/plans/2026-02-14-p6-002-p6-004-news-design.md`.
- 2026-02-14: Implementation started (this session).
- 2026-02-14: Added failing tests for ingestion/tagging/summarizer modules and confirmed expected module-missing failures.
- 2026-02-14: Implemented:
  - `services/news_ingestion/ingestion_service.py`
  - `services/news_ingestion/tagging_relevance.py`
  - `services/news_summarizer/summarizer_service.py`
  - package exports in `services/news_ingestion/__init__.py` and `services/news_summarizer/__init__.py`
- 2026-02-14: Updated docs and phase tracking (`README.md`, AGENT docs, runtime baseline, implementation plan).
- 2026-02-14: Verification complete:
  - `uv run pytest tests/test_p6_ingestion_service.py tests/test_p6_tagging_relevance.py tests/test_p6_summarizer_service.py tests/test_p6_connector_docs.py -q`
  - `uv run pytest -q`
  - `uv run ruff check .`
  - `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`
