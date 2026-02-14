# P3-007 LLM Prompt/Response Persistence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Persist full LLM prompt/response payloads plus token/cost/latency/trace metadata for each gateway call outcome.

**Architecture:** Extend `services/llm_gateway` with a persistence boundary module (`LLMCallStore` protocol + `LLMCallRecord`) and wire `LLMGateway` to emit immutable call records after successful responses and terminal failures. Keep persistence adapter-agnostic so DB implementations can be added later without modifying gateway routing logic.

**Tech Stack:** Python 3.13+, pytest, dataclasses, async protocols, UUID/time utilities.

---

### Task 1: Add failing tests for persistence behavior

**Files:**
- Create: `/Users/kai/Desktop/openTrader/tests/test_p3_llm_persistence.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_gateway_persists_successful_prompt_and_response_payloads() -> None:
    gateway = LLMGateway(settings=settings, provider_clients=clients, call_store=store)
    await gateway.generate(request)
    assert store.records[0].prompt_payload["messages"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_llm_persistence.py -v`
Expected: FAIL because persistence contracts are missing.

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True, slots=True)
class LLMCallRecord: ...

class LLMCallStore(Protocol):
    async def persist_call(self, record: LLMCallRecord) -> None: ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_llm_persistence.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/tests/test_p3_llm_persistence.py /Users/kai/Desktop/openTrader/services/llm_gateway/persistence.py
git commit -m "test(llm-gateway): add prompt-response persistence behavior coverage"
```

### Task 2: Implement gateway persistence integration

**Files:**
- Create: `/Users/kai/Desktop/openTrader/services/llm_gateway/persistence.py`
- Modify: `/Users/kai/Desktop/openTrader/services/llm_gateway/contracts.py`
- Modify: `/Users/kai/Desktop/openTrader/services/llm_gateway/gateway.py`
- Modify: `/Users/kai/Desktop/openTrader/services/llm_gateway/__init__.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_gateway_persists_failure_record_when_all_providers_exhausted() -> None:
    with pytest.raises(LLMRetryExhaustedError):
        await gateway.generate(request)
    assert store.records[0].response_payload["status"] == "failed"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_llm_persistence.py -v`
Expected: FAIL until gateway emits records.

**Step 3: Write minimal implementation**

```python
class LLMGateway:
    # optional call_store
    # persist success/failure records with trace/decision/strategy/agent/provider/model payloads and metrics
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_llm_persistence.py /Users/kai/Desktop/openTrader/tests/test_p3_llm_gateway.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/services/llm_gateway/persistence.py /Users/kai/Desktop/openTrader/services/llm_gateway/contracts.py /Users/kai/Desktop/openTrader/services/llm_gateway/gateway.py /Users/kai/Desktop/openTrader/services/llm_gateway/__init__.py
git commit -m "feat(llm-gateway): persist full prompt-response audit records"
```

### Task 3: Documentation + tracker updates

**Files:**
- Create: `/Users/kai/Desktop/openTrader/tests/test_p3_llm_persistence_docs.py`
- Modify: `/Users/kai/Desktop/openTrader/docs/llm_gateway_baseline.md`
- Create: `/Users/kai/Desktop/openTrader/docs/learning/2026-02-14-p3-llm-persistence-instincts.md`
- Modify: `/Users/kai/Desktop/openTrader/docs/agent_runtime_baseline.md`
- Modify: `/Users/kai/Desktop/openTrader/README.md`
- Modify: `/Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md`

**Step 1: Write the failing test**

```python
def test_readme_mentions_llm_persistence_module() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "services/llm_gateway/persistence.py" in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_llm_persistence_docs.py -v`
Expected: FAIL because docs and references are missing.

**Step 3: Write minimal implementation**

- Extend gateway docs with persistence contract and call-record schema.
- Add continuous-learning-v2 notes for prompt/response audit instincts.
- Update `IMPLEMENTATION_PLAN.md`:
  - Mark `P3-007` as `DONE`.
  - Append turn update + progress ledger row.
  - Advance next tasks to `P3-008`, `P3-009`, `P3-010`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/tests/test_p3_llm_persistence_docs.py /Users/kai/Desktop/openTrader/docs/llm_gateway_baseline.md /Users/kai/Desktop/openTrader/docs/learning/2026-02-14-p3-llm-persistence-instincts.md /Users/kai/Desktop/openTrader/docs/agent_runtime_baseline.md /Users/kai/Desktop/openTrader/README.md /Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md
git commit -m "docs: record p3-007 prompt-response persistence completion"
```
