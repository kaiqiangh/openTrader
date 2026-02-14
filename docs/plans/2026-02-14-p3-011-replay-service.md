# P3-011 Replay Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a deterministic replay service that reconstructs decision graphs and payload bundles from persisted traces and LLM call records.

**Architecture:** Add a `replay_service` module in `services/agent_orchestrator` with typed trace/graph contracts and a storage protocol boundary. The service will load decision trace metadata, agent runs/messages, optional long-term memory summaries, and persisted `llm_calls`, then emit an ordered replay artifact plus deterministic digest for audit and debugging.

**Tech Stack:** Python 3.13+, dataclasses, async protocols, pytest, hashlib/json.

---

### Task 1: Add failing replay-service tests

**Files:**
- Create: `/Users/kai/Desktop/openTrader/tests/test_p3_replay_service.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_replay_service_reconstructs_decision_graph_and_payloads() -> None:
    replay = await service.replay_decision(decision_id="...")
    assert replay.graph_nodes
    assert replay.graph_edges
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_replay_service.py -v`
Expected: FAIL because replay service module does not exist.

**Step 3: Write minimal implementation**

```python
class DecisionReplayService:
    async def replay_decision(self, *, decision_id: str) -> DecisionReplayResult:
        ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_replay_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/tests/test_p3_replay_service.py
git commit -m "test(agent-runtime): add replay service coverage"
```

### Task 2: Implement replay service contracts and deterministic digest

**Files:**
- Create: `/Users/kai/Desktop/openTrader/services/agent_orchestrator/replay_service.py`
- Modify: `/Users/kai/Desktop/openTrader/services/agent_orchestrator/__init__.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_replay_service_digest_is_deterministic_for_same_payload() -> None:
    first = await service.replay_decision(decision_id="...")
    second = await service.replay_decision(decision_id="...")
    assert first.deterministic_digest == second.deterministic_digest
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_replay_service.py -v`
Expected: FAIL until service and contracts are implemented.

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True, slots=True)
class DecisionReplayResult: ...

class DecisionReplayService:
    async def replay_decision(...):
        # load trace, runs/messages, llm calls, memory summary
        # build ordered nodes/edges
        # compute stable digest
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_replay_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/services/agent_orchestrator/replay_service.py /Users/kai/Desktop/openTrader/services/agent_orchestrator/__init__.py /Users/kai/Desktop/openTrader/tests/test_p3_replay_service.py
git commit -m "feat(agent-runtime): add deterministic decision replay service"
```

### Task 3: Documentation and tracker updates

**Files:**
- Modify: `/Users/kai/Desktop/openTrader/tests/test_p3_agent_runtime_docs.py`
- Modify: `/Users/kai/Desktop/openTrader/docs/agent_runtime_baseline.md`
- Modify: `/Users/kai/Desktop/openTrader/README.md`
- Create: `/Users/kai/Desktop/openTrader/docs/learning/2026-02-14-p3-replay-service-instincts.md`
- Modify: `/Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md`

**Step 1: Write the failing test**

```python
def test_agent_runtime_doc_mentions_replay_service_module() -> None:
    content = Path("docs/agent_runtime_baseline.md").read_text(encoding="utf-8")
    assert "replay_service.py" in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests/test_p3_agent_runtime_docs.py -v`
Expected: FAIL because replay service references are missing.

**Step 3: Write minimal implementation**

- Add replay service section to runtime baseline and README.
- Add continuous-learning-v2 replay-service notes.
- Update `IMPLEMENTATION_PLAN.md`:
  - Mark `P3-011` as `DONE`.
  - Append turn ledger and turn update.
  - Advance next actions to `P3-012`, `P4-001`, `P4-002`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest /Users/kai/Desktop/openTrader/tests -v`
Expected: PASS

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/tests/test_p3_agent_runtime_docs.py /Users/kai/Desktop/openTrader/docs/agent_runtime_baseline.md /Users/kai/Desktop/openTrader/README.md /Users/kai/Desktop/openTrader/docs/learning/2026-02-14-p3-replay-service-instincts.md /Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md
git commit -m "docs: record p3-011 replay service completion"
```
