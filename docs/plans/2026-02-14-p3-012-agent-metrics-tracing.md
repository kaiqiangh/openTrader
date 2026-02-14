# P3-012 Agent Metrics and Tracing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Instrument agent runtime with stage latency/failure metrics and LLM token-consumption telemetry for observability.

**Architecture:** Add a focused `metrics_tracing` module under `services/agent_orchestrator` with in-memory metric/tracing contracts and snapshots. Wire `AgentOrchestrator` stage execution through metric recording wrappers (success/failure latency) and wire `LLMGateway` token/cost/latency outcomes into the same metrics collector via an optional sink contract.

**Tech Stack:** Python 3.13+, dataclasses, async protocols, pytest.

---

### Task 1: Add failing tests for metrics/tracing behavior

**Files:**
- Create: `/Users/kai/Desktop/openTrader/tests/test_p3_metrics_tracing.py`
- Modify: `/Users/kai/Desktop/openTrader/tests/test_p3_orchestrator.py`
- Modify: `/Users/kai/Desktop/openTrader/tests/test_p3_llm_gateway.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_orchestrator_records_stage_latency_and_failures() -> None:
    await orchestrator.handle_market_event(...)
    snapshot = metrics.snapshot()
    assert snapshot["agent_stages"]["planner_agent"]["runs_total"] == 1
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_metrics_tracing.py /Users/kai/Desktop/openTrader/tests/test_p3_orchestrator.py /Users/kai/Desktop/openTrader/tests/test_p3_llm_gateway.py -v`
Expected: FAIL because metrics module and instrumentation wiring do not exist.

**Step 3: Write minimal implementation**

```python
class AgentRuntimeMetrics:
    def record_stage_success(...): ...
    def record_stage_failure(...): ...
    def record_llm_call(...): ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_metrics_tracing.py /Users/kai/Desktop/openTrader/tests/test_p3_orchestrator.py /Users/kai/Desktop/openTrader/tests/test_p3_llm_gateway.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/tests/test_p3_metrics_tracing.py /Users/kai/Desktop/openTrader/tests/test_p3_orchestrator.py /Users/kai/Desktop/openTrader/tests/test_p3_llm_gateway.py
git commit -m "test(agent-runtime): add metrics and tracing coverage"
```

### Task 2: Implement metrics module and runtime integrations

**Files:**
- Create: `/Users/kai/Desktop/openTrader/services/agent_orchestrator/metrics_tracing.py`
- Modify: `/Users/kai/Desktop/openTrader/services/agent_orchestrator/orchestrator.py`
- Modify: `/Users/kai/Desktop/openTrader/services/llm_gateway/contracts.py`
- Modify: `/Users/kai/Desktop/openTrader/services/llm_gateway/gateway.py`
- Modify: `/Users/kai/Desktop/openTrader/services/agent_orchestrator/__init__.py`

**Step 1: Write the failing test**

```python
def test_metrics_snapshot_exposes_latency_failure_and_token_totals() -> None:
    snapshot = metrics.snapshot()
    assert "agent_stages" in snapshot
    assert "llm_usage" in snapshot
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_metrics_tracing.py -v`
Expected: FAIL until module contracts and integrations are implemented.

**Step 3: Write minimal implementation**

```python
class AgentRuntimeMetrics:
    def snapshot(self) -> dict[str, object]: ...

class AgentOrchestrator:
    # wrap planner/risk/execution/guardrail stages with latency + failure recording

class LLMGateway:
    # optional metrics sink for token/cost/latency outcomes
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_metrics_tracing.py /Users/kai/Desktop/openTrader/tests/test_p3_orchestrator.py /Users/kai/Desktop/openTrader/tests/test_p3_llm_gateway.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/services/agent_orchestrator/metrics_tracing.py /Users/kai/Desktop/openTrader/services/agent_orchestrator/orchestrator.py /Users/kai/Desktop/openTrader/services/llm_gateway/contracts.py /Users/kai/Desktop/openTrader/services/llm_gateway/gateway.py /Users/kai/Desktop/openTrader/services/agent_orchestrator/__init__.py
git commit -m "feat(agent-runtime): add metrics and tracing instrumentation baseline"
```

### Task 3: Documentation and tracker updates

**Files:**
- Modify: `/Users/kai/Desktop/openTrader/tests/test_p3_agent_runtime_docs.py`
- Modify: `/Users/kai/Desktop/openTrader/docs/agent_runtime_baseline.md`
- Modify: `/Users/kai/Desktop/openTrader/README.md`
- Create: `/Users/kai/Desktop/openTrader/docs/learning/2026-02-14-p3-metrics-tracing-instincts.md`
- Modify: `/Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md`

**Step 1: Write the failing test**

```python
def test_agent_runtime_doc_mentions_metrics_tracing_module() -> None:
    content = Path("docs/agent_runtime_baseline.md").read_text(encoding="utf-8")
    assert "metrics_tracing.py" in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_agent_runtime_docs.py -v`
Expected: FAIL because P3-012 references are missing.

**Step 3: Write minimal implementation**

- Document metrics/tracing module and contracts in runtime baseline.
- Add continuous-learning-v2 metrics/tracing instincts.
- Update `IMPLEMENTATION_PLAN.md`:
  - Mark `P3-012` as `DONE`.
  - Append turn update + progress ledger row.
  - Advance next actions to `P4-001`, `P4-002`, `P4-003`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/tests/test_p3_agent_runtime_docs.py /Users/kai/Desktop/openTrader/docs/agent_runtime_baseline.md /Users/kai/Desktop/openTrader/README.md /Users/kai/Desktop/openTrader/docs/learning/2026-02-14-p3-metrics-tracing-instincts.md /Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md
git commit -m "docs: record p3-012 metrics and tracing completion"
```
