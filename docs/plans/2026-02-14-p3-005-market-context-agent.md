# P3-005 Market Context Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a dedicated market context agent that enriches canonical market events with microstructure and news context before planner/risk/execution decision processing.

**Architecture:** Introduce `MarketContextAgent` as a deterministic enrichment module under `services/agent_orchestrator`. The orchestrator will invoke this agent after envelope validation, emit a `context_enriched` lifecycle event, and pass enriched context into planner/risk/execution-decision modules. Contracts will include a typed context output so downstream consumers and replay tooling can rely on a stable schema.

**Tech Stack:** Python 3.13+, pytest, dataclasses, existing envelope validation contracts.

---

### Task 1: Add failing tests for market context enrichment and orchestrator integration

**Files:**
- Create: `tests/test_p3_market_context_agent.py`
- Modify: `tests/test_p3_orchestrator.py`
- Modify: `tests/test_p3_agent_runtime_docs.py`

**Step 1: Write the failing test**

```python
def test_market_context_enriches_microstructure_and_news_payload() -> None:
    agent = MarketContextAgent()
    result = agent.enrich(payload=payload, strategy=strategy)
    assert result.context["microstructure_regime"] == "bid_dominant"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p3_market_context_agent.py tests/test_p3_orchestrator.py tests/test_p3_agent_runtime_docs.py -v`
Expected: FAIL because `market_context_agent.py` and new context contract fields are missing.

**Step 3: Write minimal implementation**

```python
class MarketContextAgent:
    def enrich(self, *, payload: Mapping[str, Any], strategy: StrategyConfig) -> MarketContextOutput:
        ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p3_market_context_agent.py tests/test_p3_orchestrator.py tests/test_p3_agent_runtime_docs.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_p3_market_context_agent.py tests/test_p3_orchestrator.py tests/test_p3_agent_runtime_docs.py
git commit -m "test(agent-runtime): add market context enrichment coverage"
```

### Task 2: Implement P3-005 market context agent

**Files:**
- Create: `services/agent_orchestrator/market_context_agent.py`
- Modify: `services/agent_orchestrator/contracts.py`
- Modify: `services/agent_orchestrator/orchestrator.py`
- Modify: `services/agent_orchestrator/__init__.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_orchestrator_emits_context_enriched_stage() -> None:
    result = await orchestrator.handle_market_event(envelope, strategy=strategy)
    assert "agent.decision.context_enriched" in [item["event_type"] for item in result.lifecycle]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p3_market_context_agent.py tests/test_p3_orchestrator.py -v`
Expected: FAIL because orchestrator does not integrate market context agent.

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True, slots=True)
class MarketContextOutput:
    context: dict[str, Any]
    microstructure: dict[str, Any]
    news: dict[str, Any]
    quality: dict[str, Any]
    notes: tuple[str, ...]
```

```python
class AgentOrchestrator:
    # envelope -> market context enrichment -> planner -> risk -> execution decision
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p3_market_context_agent.py tests/test_p3_orchestrator.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services/agent_orchestrator/market_context_agent.py services/agent_orchestrator/contracts.py services/agent_orchestrator/orchestrator.py services/agent_orchestrator/__init__.py
git commit -m "feat(agent-runtime): add market context enrichment agent"
```

### Task 3: Documentation + tracker updates

**Files:**
- Modify: `docs/agent_runtime_baseline.md`
- Create: `docs/learning/2026-02-14-p3-market-context-instincts.md`
- Modify: `README.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

**Step 1: Write the failing test**

```python
def test_readme_mentions_market_context_agent_module() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "services/agent_orchestrator/market_context_agent.py" in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p3_agent_runtime_docs.py -v`
Expected: FAIL because docs do not yet reference `P3-005` module and instincts.

**Step 3: Write minimal implementation**

- Update runtime baseline docs with market context enrichment contract and lifecycle stage.
- Add continuous-learning-v2 instincts for optional news-aware context enrichment.
- Update `IMPLEMENTATION_PLAN.md`:
  - Mark `P3-005` as `DONE`.
  - Append new turn update + progress ledger row.
  - Advance immediate next actions to `P3-006`, `P3-007`, `P3-008`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests -v`
Expected: PASS

**Step 5: Commit**

```bash
git add docs/agent_runtime_baseline.md docs/learning/2026-02-14-p3-market-context-instincts.md README.md docs/IMPLEMENTATION_PLAN.md
git commit -m "docs: record p3-005 market context baseline completion"
```
