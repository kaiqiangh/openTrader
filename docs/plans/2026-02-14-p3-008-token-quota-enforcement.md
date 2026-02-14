# P3-008 Token Quota Enforcement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enforce per-strategy/per-agent daily token and monthly cost hard limits in the LLM gateway before dispatching provider calls.

**Architecture:** Add a gateway-adjacent quota module with typed limit/usage contracts and a storage protocol abstraction. `LLMGateway` will query quota state pre-dispatch, block requests that exceed hard limits, and update usage on successful calls using persisted usage/cost metrics. Optional quota-blocked events will also be persisted through the existing call record boundary.

**Tech Stack:** Python 3.13+, pytest, dataclasses, async protocols.

---

### Task 1: Add failing tests for quota enforcement behavior

**Files:**
- Create: `/Users/kai/Desktop/openTrader/tests/test_p3_llm_quota_enforcement.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_gateway_blocks_when_daily_token_limit_exceeded() -> None:
    with pytest.raises(LLMQuotaExceededError):
        await gateway.generate(request)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_llm_quota_enforcement.py -v`
Expected: FAIL because quota contracts and gateway integration are missing.

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True, slots=True)
class QuotaLimits: ...
@dataclass(frozen=True, slots=True)
class QuotaUsage: ...
class LLMQuotaStore(Protocol): ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_llm_quota_enforcement.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/tests/test_p3_llm_quota_enforcement.py /Users/kai/Desktop/openTrader/services/llm_gateway/quota.py
git commit -m "test(llm-gateway): add hard-limit quota enforcement coverage"
```

### Task 2: Implement quota module and gateway integration

**Files:**
- Create: `/Users/kai/Desktop/openTrader/services/llm_gateway/quota.py`
- Modify: `/Users/kai/Desktop/openTrader/services/llm_gateway/contracts.py`
- Modify: `/Users/kai/Desktop/openTrader/services/llm_gateway/gateway.py`
- Modify: `/Users/kai/Desktop/openTrader/services/llm_gateway/__init__.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_gateway_increments_quota_usage_on_success() -> None:
    await gateway.generate(request)
    assert quota_store.usage.total_tokens > 0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_llm_quota_enforcement.py /Users/kai/Desktop/openTrader/tests/test_p3_llm_gateway.py -v`
Expected: FAIL until gateway applies quota checks and usage updates.

**Step 3: Write minimal implementation**

```python
class LLMGateway:
    # optional quota_store
    # pre-dispatch hard-limit checks
    # usage increment after successful response
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_llm_quota_enforcement.py /Users/kai/Desktop/openTrader/tests/test_p3_llm_gateway.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/services/llm_gateway/quota.py /Users/kai/Desktop/openTrader/services/llm_gateway/contracts.py /Users/kai/Desktop/openTrader/services/llm_gateway/gateway.py /Users/kai/Desktop/openTrader/services/llm_gateway/__init__.py
git commit -m "feat(llm-gateway): enforce token and cost hard limits"
```

### Task 3: Documentation + tracker updates

**Files:**
- Create: `/Users/kai/Desktop/openTrader/tests/test_p3_llm_quota_docs.py`
- Modify: `/Users/kai/Desktop/openTrader/docs/llm_gateway_baseline.md`
- Create: `/Users/kai/Desktop/openTrader/docs/learning/2026-02-14-p3-llm-quota-instincts.md`
- Modify: `/Users/kai/Desktop/openTrader/docs/agent_runtime_baseline.md`
- Modify: `/Users/kai/Desktop/openTrader/README.md`
- Modify: `/Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md`

**Step 1: Write the failing test**

```python
def test_readme_mentions_llm_quota_module() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "services/llm_gateway/quota.py" in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_llm_quota_docs.py -v`
Expected: FAIL because docs and references are missing.

**Step 3: Write minimal implementation**

- Update gateway docs with quota contracts and hard-limit flow.
- Add continuous-learning-v2 quota enforcement instincts.
- Update `IMPLEMENTATION_PLAN.md`:
  - Mark `P3-008` as `DONE`.
  - Append turn update + progress ledger row.
  - Advance next tasks to `P3-009`, `P3-010`, `P3-011`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/tests/test_p3_llm_quota_docs.py /Users/kai/Desktop/openTrader/docs/llm_gateway_baseline.md /Users/kai/Desktop/openTrader/docs/learning/2026-02-14-p3-llm-quota-instincts.md /Users/kai/Desktop/openTrader/docs/agent_runtime_baseline.md /Users/kai/Desktop/openTrader/README.md /Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md
git commit -m "docs: record p3-008 quota enforcement completion"
```
