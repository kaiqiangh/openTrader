# P2-001 P2-002 P2-003 Market Ingestion Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the first Phase 2 market-ingestion building blocks: a CCXT-style adapter with REST snapshot bootstrap, a resilience/backoff manager, and an order-book sync engine with sequence-gap detection.

**Architecture:** Build a small layered backend module (`contracts -> adapter -> resilience -> sync engine`) so each concern is independently testable and reusable by future ingestion workers. Follow @backend-patterns via clear component boundaries and @api-design by enforcing deterministic input/output contracts and typed error semantics for adapter outputs. Capture learning artifacts using @continuous-learning-v2 style atomic instincts in project docs for reuse.

**Tech Stack:** Python 3.13+, pytest, dataclasses, typing Protocols, Markdown docs.

---

### Task 1: P2-001 CCXT-Style Ingestion Adapter + Snapshot Bootstrap

**Files:**
- Create: `tests/test_p2_ingestion_adapter.py`
- Create: `services/market_ingestion/__init__.py`
- Create: `services/market_ingestion/contracts.py`
- Create: `services/market_ingestion/exchange_adapter.py`

**Step 1: Write the failing test**

```python
async def test_bootstrap_snapshot_normalizes_levels() -> None:
    adapter = CCXTIngestionAdapter(exchange="binance", rest_client=fake_rest, ws_client=fake_ws)
    snapshot = await adapter.bootstrap_snapshot("BTC/USDT", limit=5)
    assert snapshot.exchange == "binance"
    assert snapshot.symbol == "BTC/USDT"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p2_ingestion_adapter.py -v`
Expected: FAIL because adapter module does not exist.

**Step 3: Write minimal implementation**

```python
class CCXTIngestionAdapter:
    async def bootstrap_snapshot(self, symbol: str, limit: int = 200) -> OrderBookSnapshot: ...
    async def poll_delta(self, symbol: str, limit: int = 200) -> OrderBookDelta: ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p2_ingestion_adapter.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_p2_ingestion_adapter.py services/market_ingestion/__init__.py services/market_ingestion/contracts.py services/market_ingestion/exchange_adapter.py
git commit -m "feat(ingestion): add ccxt-style adapter and snapshot bootstrap"
```

### Task 2: P2-002 Connection Resilience + Reconnect Backoff

**Files:**
- Create: `tests/test_p2_connection_resilience.py`
- Create: `services/market_ingestion/connection_resilience.py`
- Modify: `services/market_ingestion/__init__.py`

**Step 1: Write the failing test**

```python
def test_next_backoff_grows_with_attempts_and_cap() -> None:
    manager = ConnectionResilienceManager(config=BackoffConfig(...))
    assert manager.next_backoff_seconds(attempt=1) < manager.next_backoff_seconds(attempt=3)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p2_connection_resilience.py -v`
Expected: FAIL because resilience module is missing.

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class BackoffConfig: ...

class ConnectionResilienceManager:
    def mark_heartbeat(self, now_seconds: float) -> None: ...
    def is_stale(self, now_seconds: float) -> bool: ...
    def next_backoff_seconds(self, attempt: int) -> float: ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p2_connection_resilience.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_p2_connection_resilience.py services/market_ingestion/connection_resilience.py services/market_ingestion/__init__.py
git commit -m "feat(ingestion): add connection resilience and reconnect backoff"
```

### Task 3: P2-003 Order Book Sync Engine with Sequence Handling

**Files:**
- Create: `tests/test_p2_order_book_sync.py`
- Create: `services/market_ingestion/order_book_sync.py`
- Modify: `services/market_ingestion/__init__.py`

**Step 1: Write the failing test**

```python
def test_apply_delta_raises_gap_error_when_sequence_skips() -> None:
    engine.load_snapshot(snapshot_with_sequence_100)
    with pytest.raises(OrderBookSequenceGapError):
        engine.apply_delta(delta_with_sequence_start_105)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p2_order_book_sync.py -v`
Expected: FAIL because sync engine module does not exist.

**Step 3: Write minimal implementation**

```python
class OrderBookSyncEngine:
    def load_snapshot(self, snapshot: OrderBookSnapshot) -> None: ...
    def apply_delta(self, delta: OrderBookDelta) -> bool: ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p2_order_book_sync.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_p2_order_book_sync.py services/market_ingestion/order_book_sync.py services/market_ingestion/__init__.py
git commit -m "feat(ingestion): add order book sync engine with sequence gap detection"
```

### Task 4: Update Docs + Learning Artifacts + Progress Tracker

**Files:**
- Create: `docs/market_ingestion_foundation.md`
- Create: `docs/learning/2026-02-14-p2-ingestion-instincts.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Modify: `README.md`

**Step 1: Write the failing test**

```python
def test_market_ingestion_foundation_doc_exists() -> None:
    assert Path("docs/market_ingestion_foundation.md").exists()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p2_ingestion_docs.py -v`
Expected: FAIL because docs are missing.

**Step 3: Write minimal implementation**

- Add docs for module boundaries, event contracts, and usage flow.
- Add continuous-learning-v2 style instinct notes.
- Update `docs/IMPLEMENTATION_PLAN.md` turn ledger + statuses for P2-001, P2-002, P2-003.
- Update README with new Phase 2 foundation files.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests -v`
Expected: PASS

**Step 5: Commit**

```bash
git add docs/market_ingestion_foundation.md docs/learning/2026-02-14-p2-ingestion-instincts.md docs/IMPLEMENTATION_PLAN.md README.md tests
git commit -m "docs: record p2 market ingestion foundation and progress"
```
