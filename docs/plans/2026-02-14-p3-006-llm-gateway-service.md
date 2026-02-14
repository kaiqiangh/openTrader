# P3-006 LLM Gateway Service Skeleton Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver a centralized LLM gateway skeleton with provider configuration, timeout enforcement, retry policy, and provider fallback routing.

**Architecture:** Create a standalone `services/llm_gateway` package with typed request/response contracts and a protocol-based provider client abstraction. `LLMGateway` will execute calls through ordered providers, apply per-provider timeout/retry settings, and expose deterministic metadata (attempt count, provider alias, latency) for later persistence work in `P3-007`.

**Tech Stack:** Python 3.13+, pytest, dataclasses, asyncio timeout/retry primitives.

---

### Task 1: Add failing tests for gateway behavior

**Files:**
- Create: `/Users/kai/Desktop/openTrader/tests/test_p3_llm_gateway.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_gateway_retries_transient_provider_failure_then_succeeds() -> None:
    gateway = LLMGateway(settings=settings, provider_clients={"primary": flaky_client})
    response = await gateway.generate(request)
    assert response.attempt_count == 2
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_llm_gateway.py -v`
Expected: FAIL because `services/llm_gateway` modules do not exist.

**Step 3: Write minimal implementation**

```python
class LLMGateway:
    async def generate(self, request: LLMRequest, provider_order: Sequence[str] | None = None) -> LLMResponse:
        ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_llm_gateway.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/tests/test_p3_llm_gateway.py /Users/kai/Desktop/openTrader/services/llm_gateway
 git commit -m "feat(llm-gateway): add retry-timeout-fallback gateway skeleton"
```

### Task 2: Implement contracts and gateway package

**Files:**
- Create: `/Users/kai/Desktop/openTrader/services/llm_gateway/contracts.py`
- Create: `/Users/kai/Desktop/openTrader/services/llm_gateway/gateway.py`
- Create: `/Users/kai/Desktop/openTrader/services/llm_gateway/__init__.py`

**Step 1: Write the failing test**

```python
def test_gateway_response_contains_provider_model_and_latency() -> None:
    response = await gateway.generate(request)
    assert response.provider == "primary"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_llm_gateway.py -v`
Expected: FAIL due missing contracts and gateway implementation.

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True, slots=True)
class ProviderSettings: ...
@dataclass(frozen=True, slots=True)
class GatewaySettings: ...
@dataclass(frozen=True, slots=True)
class LLMRequest: ...
@dataclass(frozen=True, slots=True)
class LLMResponse: ...

class LLMGatewayError(RuntimeError): ...
class ProviderNotConfiguredError(LLMGatewayError): ...
class LLMRetryExhaustedError(LLMGatewayError): ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_llm_gateway.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/services/llm_gateway/contracts.py /Users/kai/Desktop/openTrader/services/llm_gateway/gateway.py /Users/kai/Desktop/openTrader/services/llm_gateway/__init__.py
git commit -m "feat(llm-gateway): add typed contracts and provider routing skeleton"
```

### Task 3: Documentation and tracker updates

**Files:**
- Create: `/Users/kai/Desktop/openTrader/tests/test_p3_llm_gateway_docs.py`
- Create: `/Users/kai/Desktop/openTrader/docs/llm_gateway_baseline.md`
- Create: `/Users/kai/Desktop/openTrader/docs/learning/2026-02-14-p3-llm-gateway-instincts.md`
- Modify: `/Users/kai/Desktop/openTrader/docs/agent_runtime_baseline.md`
- Modify: `/Users/kai/Desktop/openTrader/README.md`
- Modify: `/Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md`

**Step 1: Write the failing test**

```python
def test_readme_mentions_llm_gateway_modules() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "services/llm_gateway/gateway.py" in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_llm_gateway_docs.py -v`
Expected: FAIL because docs and references are missing.

**Step 3: Write minimal implementation**

- Add `docs/llm_gateway_baseline.md` describing provider config, retry/timeout policy, and fallback behavior.
- Add continuous-learning-v2 notes for gateway reliability instincts.
- Update `IMPLEMENTATION_PLAN.md`:
  - Mark `P3-006` as `DONE`.
  - Append new turn update + progress ledger row.
  - Advance next actions to `P3-007`, `P3-008`, `P3-009`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/tests/test_p3_llm_gateway_docs.py /Users/kai/Desktop/openTrader/docs/llm_gateway_baseline.md /Users/kai/Desktop/openTrader/docs/learning/2026-02-14-p3-llm-gateway-instincts.md /Users/kai/Desktop/openTrader/docs/agent_runtime_baseline.md /Users/kai/Desktop/openTrader/README.md /Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md
git commit -m "docs: record p3-006 llm gateway baseline completion"
```
