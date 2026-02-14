# P3-010 Memory Layer Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement short-term Redis-style decision memory and long-term Postgres-style decision memory persistence/read paths for the Phase 3 orchestrator.

**Architecture:** Add a dedicated memory layer module with explicit short-term and long-term store protocols. Integrate the layer into `AgentOrchestrator` so each decision cycle hydrates prior memory, writes stage outputs to short-term memory slots, and persists a deterministic decision summary for long-term replay.

**Tech Stack:** Python 3.13+, dataclasses, asyncio protocols, pytest.

---

### Task 1: Add failing tests for memory layer contracts and fallback behavior

**Files:**
- Create: `tests/test_p3_memory_layer.py`

**Step 1: Write the failing test**

```python
def test_memory_layer_reads_short_term_slot_first() -> None:
    snapshot = await layer.read_decision_memory(...)
    assert snapshot.source == "redis"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p3_memory_layer.py -v`
Expected: FAIL because memory layer module does not exist.

**Step 3: Write minimal implementation**

```python
class AgentMemoryLayer:
    async def read_decision_memory(...):
        ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p3_memory_layer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_p3_memory_layer.py
git commit -m "test(agent-runtime): add memory layer contract coverage"
```

### Task 2: Integrate memory layer writes/reads into orchestrator flow

**Files:**
- Modify: `tests/test_p3_orchestrator.py`
- Modify: `services/agent_orchestrator/orchestrator.py`
- Create: `services/agent_orchestrator/memory_layer.py`
- Modify: `services/agent_orchestrator/__init__.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_orchestrator_writes_memory_slots_and_persists_summary() -> None:
    result = await orchestrator.handle_market_event(...)
    assert long_term_store.records[0].status == result.status
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p3_orchestrator.py tests/test_p3_memory_layer.py -v`
Expected: FAIL until memory layer integration exists.

**Step 3: Write minimal implementation**

```python
await self.memory_layer.write_decision_slot(slot="plan", payload={...})
await self.memory_layer.persist_decision_summary(...)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p3_orchestrator.py tests/test_p3_memory_layer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services/agent_orchestrator/memory_layer.py services/agent_orchestrator/orchestrator.py services/agent_orchestrator/__init__.py tests/test_p3_orchestrator.py tests/test_p3_memory_layer.py
git commit -m "feat(agent-runtime): integrate short and long term decision memory"
```

### Task 3: Documentation and tracker updates

**Files:**
- Modify: `tests/test_p3_agent_runtime_docs.py`
- Modify: `docs/agent_runtime_baseline.md`
- Modify: `README.md`
- Create: `docs/learning/2026-02-14-p3-memory-layer-instincts.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

**Step 1: Write the failing test**

```python
def test_agent_runtime_doc_mentions_memory_layer_module() -> None:
    assert "memory_layer.py" in Path("docs/agent_runtime_baseline.md").read_text()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p3_agent_runtime_docs.py -v`
Expected: FAIL because docs are missing memory-layer references.

**Step 3: Write minimal implementation**

- Document memory contracts in runtime baseline.
- Add continuous-learning-v2 memory-layer notes.
- Update `IMPLEMENTATION_PLAN.md` turn ledger and set `P3-010` to `DONE`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_p3_agent_runtime_docs.py docs/agent_runtime_baseline.md README.md docs/learning/2026-02-14-p3-memory-layer-instincts.md docs/IMPLEMENTATION_PLAN.md
git commit -m "docs: record p3-010 memory integration completion"
```
