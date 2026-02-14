# P3-009 Guardrail Validation Layer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a guardrail validation layer that blocks invalid execution decisions based on schema, risk policy, symbol constraints, leverage, and confidence thresholds.

**Architecture:** Add a dedicated `guardrail_validation` module under `services/agent_orchestrator` with explicit result/violation contracts. Integrate the guardrail layer into `AgentOrchestrator` between execution decision proposal and execution intent publish, emitting lifecycle events for pass/reject outcomes and suppressing publish on rejection.

**Tech Stack:** Python 3.13+, pytest, dataclasses, existing agent runtime contracts.

---

### Task 1: Add failing tests for guardrail behavior and orchestrator flow

**Files:**
- Create: `/Users/kai/Desktop/openTrader/tests/test_p3_guardrail_validation.py`
- Modify: `/Users/kai/Desktop/openTrader/tests/test_p3_orchestrator.py`
- Modify: `/Users/kai/Desktop/openTrader/tests/test_p3_agent_runtime_docs.py`

**Step 1: Write the failing test**

```python
def test_guardrail_rejects_low_confidence_buy_decision() -> None:
    result = layer.validate(...)
    assert result.allowed is False
    assert "confidence_threshold" in result.blocked_by
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_guardrail_validation.py /Users/kai/Desktop/openTrader/tests/test_p3_orchestrator.py /Users/kai/Desktop/openTrader/tests/test_p3_agent_runtime_docs.py -v`
Expected: FAIL because guardrail module/contracts are missing.

**Step 3: Write minimal implementation**

```python
class GuardrailValidationLayer:
    def validate(... ) -> GuardrailValidationResult:
        ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_guardrail_validation.py /Users/kai/Desktop/openTrader/tests/test_p3_orchestrator.py /Users/kai/Desktop/openTrader/tests/test_p3_agent_runtime_docs.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/tests/test_p3_guardrail_validation.py /Users/kai/Desktop/openTrader/tests/test_p3_orchestrator.py /Users/kai/Desktop/openTrader/tests/test_p3_agent_runtime_docs.py
git commit -m "test(agent-runtime): add guardrail validation coverage"
```

### Task 2: Implement guardrail contracts and integration

**Files:**
- Create: `/Users/kai/Desktop/openTrader/services/agent_orchestrator/guardrail_validation.py`
- Modify: `/Users/kai/Desktop/openTrader/services/agent_orchestrator/contracts.py`
- Modify: `/Users/kai/Desktop/openTrader/services/agent_orchestrator/orchestrator.py`
- Modify: `/Users/kai/Desktop/openTrader/services/agent_orchestrator/__init__.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_orchestrator_does_not_publish_intent_when_guardrail_rejects() -> None:
    result = await orchestrator.handle_market_event(...)
    assert result.status == "GUARDRAIL_REJECTED"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_guardrail_validation.py /Users/kai/Desktop/openTrader/tests/test_p3_orchestrator.py -v`
Expected: FAIL until orchestration guardrail step exists.

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True, slots=True)
class GuardrailValidationResult: ...

class AgentOrchestrator:
    # planner -> risk -> execution decision -> guardrail validate -> publish (if allowed)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_guardrail_validation.py /Users/kai/Desktop/openTrader/tests/test_p3_orchestrator.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/services/agent_orchestrator/guardrail_validation.py /Users/kai/Desktop/openTrader/services/agent_orchestrator/contracts.py /Users/kai/Desktop/openTrader/services/agent_orchestrator/orchestrator.py /Users/kai/Desktop/openTrader/services/agent_orchestrator/__init__.py
git commit -m "feat(agent-runtime): add guardrail validation layer before intent publish"
```

### Task 3: Documentation + tracker updates

**Files:**
- Modify: `/Users/kai/Desktop/openTrader/docs/agent_runtime_baseline.md`
- Create: `/Users/kai/Desktop/openTrader/docs/learning/2026-02-14-p3-guardrail-instincts.md`
- Modify: `/Users/kai/Desktop/openTrader/README.md`
- Modify: `/Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md`

**Step 1: Write the failing test**

```python
def test_readme_mentions_guardrail_validation_module() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "services/agent_orchestrator/guardrail_validation.py" in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_agent_runtime_docs.py -v`
Expected: FAIL because docs references are missing.

**Step 3: Write minimal implementation**

- Update runtime baseline docs with guardrail contracts and lifecycle gating.
- Add continuous-learning-v2 notes for guardrail rejection transparency.
- Update `IMPLEMENTATION_PLAN.md`:
  - Mark `P3-009` as `DONE`.
  - Append turn update + ledger row.
  - Advance next actions to `P3-010`, `P3-011`, `P3-012`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/docs/agent_runtime_baseline.md /Users/kai/Desktop/openTrader/docs/learning/2026-02-14-p3-guardrail-instincts.md /Users/kai/Desktop/openTrader/README.md /Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md
git commit -m "docs: record p3-009 guardrail validation completion"
```
