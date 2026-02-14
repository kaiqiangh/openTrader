# P3-004 Execution Decision Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a dedicated execution decision agent that converts planner+risk outputs into constrained action proposals (`BUY`/`SELL`/`HOLD`/`CLOSE`) and integrate it into orchestration intent publishing.

**Architecture:** Introduce `ExecutionDecisionAgent` as a pure deterministic module in `services/agent_orchestrator` so policy constraints are explicit before LLM integration (`P3-006`). The orchestrator will call planner -> risk -> execution decision, then publish only constrained proposals. Contracts will be extended with an execution decision dataclass so downstream modules consume a stable schema.

**Tech Stack:** Python 3.13+, pytest, dataclasses, existing message envelope validator.

---

### Task 1: Add failing tests for execution decision contract and integration

**Files:**
- Create: `tests/test_p3_execution_decision_agent.py`
- Modify: `tests/test_p3_orchestrator.py`
- Modify: `tests/test_p3_agent_runtime_docs.py`

**Step 1: Write the failing test**

```python
def test_execution_decision_proposes_hold_when_risk_not_approved() -> None:
    agent = ExecutionDecisionAgent()
    proposal = agent.propose_action(plan=plan, risk=risk, market_context=context, strategy=strategy)
    assert proposal.action == "HOLD"
    assert proposal.quantity == 0.0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p3_execution_decision_agent.py tests/test_p3_orchestrator.py tests/test_p3_agent_runtime_docs.py -v`
Expected: FAIL because `execution_decision_agent.py` and updated contracts do not exist.

**Step 3: Write minimal implementation**

```python
class ExecutionDecisionAgent:
    def propose_action(self, *, plan: PlannerDecision, risk: RiskAssessment, market_context: Mapping[str, Any], strategy: StrategyConfig) -> ExecutionDecision:
        ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p3_execution_decision_agent.py tests/test_p3_orchestrator.py tests/test_p3_agent_runtime_docs.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_p3_execution_decision_agent.py tests/test_p3_orchestrator.py tests/test_p3_agent_runtime_docs.py
git commit -m "test(agent-runtime): add execution decision agent contract coverage"
```

### Task 2: Implement P3-004 execution decision agent

**Files:**
- Create: `services/agent_orchestrator/execution_decision_agent.py`
- Modify: `services/agent_orchestrator/contracts.py`
- Modify: `services/agent_orchestrator/orchestrator.py`
- Modify: `services/agent_orchestrator/__init__.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_orchestrator_uses_execution_decision_agent_output_for_intent_payload() -> None:
    result = await orchestrator.handle_market_event(envelope, strategy=strategy)
    assert result.execution_decision.action in {"BUY", "SELL", "HOLD", "CLOSE"}
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p3_execution_decision_agent.py tests/test_p3_orchestrator.py -v`
Expected: FAIL because orchestrator result has no execution decision and no decision agent integration.

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True, slots=True)
class ExecutionDecision:
    action: DecisionAction
    quantity: float
    confidence: float
    rationale: tuple[str, ...]
    constraints: dict[str, Any]
```

```python
class AgentOrchestrator:
    # planner -> risk -> execution_decision
    # publish constrained execution.intent.created payload
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p3_execution_decision_agent.py tests/test_p3_orchestrator.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services/agent_orchestrator/execution_decision_agent.py services/agent_orchestrator/contracts.py services/agent_orchestrator/orchestrator.py services/agent_orchestrator/__init__.py
git commit -m "feat(agent-runtime): add execution decision agent with action constraints"
```

### Task 3: Documentation + tracker updates

**Files:**
- Modify: `docs/agent_runtime_baseline.md`
- Create: `docs/learning/2026-02-14-p3-execution-decision-instincts.md`
- Modify: `README.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

**Step 1: Write the failing test**

```python
def test_readme_mentions_execution_decision_agent_module() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "services/agent_orchestrator/execution_decision_agent.py" in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p3_agent_runtime_docs.py -v`
Expected: FAIL because docs do not include `P3-004` module references.

**Step 3: Write minimal implementation**

- Update runtime baseline docs with `P3-004` decision stage and constrained action schema.
- Add continuous-learning-v2 instinct notes for action constraint normalization.
- Update `IMPLEMENTATION_PLAN.md`:
  - Mark `P3-004` as `DONE`.
  - Append new turn update and progress ledger row.
  - Advance immediate next actions to `P3-005`, `P3-006`, `P3-007`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests -v`
Expected: PASS

**Step 5: Commit**

```bash
git add docs/agent_runtime_baseline.md docs/learning/2026-02-14-p3-execution-decision-instincts.md README.md docs/IMPLEMENTATION_PLAN.md
git commit -m "docs: record p3-004 execution decision baseline completion"
```
