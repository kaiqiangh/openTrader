# P2-004 P2-005 P2-006 Market Integrity and Canonical Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver Phase 2 integrity-critical ingestion modules: sequence-gap detection with resync signaling, k-line reconstruction validation, and canonical normalization/publishing to `market.canonical`.

**Architecture:** Extend the existing `services/market_ingestion` layer with three focused modules: `gap_detection`, `kline_validator`, and `canonical_pipeline`. Keep responsibilities separated: detection/validation logic remains pure and deterministic, while publishing is isolated behind a small protocol for broker adapters. Reuse the shared message envelope validator to enforce canonical event contract consistency before publish.

**Tech Stack:** Python 3.13+, pytest, dataclasses, typing Protocols, existing shared message-envelope validator.

---

### Task 1: P2-004 Gap Detection Module

**Files:**
- Create: `tests/test_p2_gap_detection.py`
- Create: `services/market_ingestion/gap_detection.py`
- Modify: `services/market_ingestion/__init__.py`

**Step 1: Write the failing test**

```python
def test_detect_gap_when_sequence_start_skips_expected() -> None:
    detector = GapDetectionModule()
    result = detector.evaluate(current_sequence=100, incoming_start=105, incoming_end=105)
    assert result.has_gap is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p2_gap_detection.py -v`
Expected: FAIL because gap detection module does not exist.

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class GapDetectionResult: ...

class GapDetectionModule:
    def evaluate(...) -> GapDetectionResult: ...
    def build_resync_request(...) -> dict[str, object]: ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p2_gap_detection.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_p2_gap_detection.py services/market_ingestion/gap_detection.py services/market_ingestion/__init__.py
git commit -m "feat(ingestion): add sequence gap detection and resync signal builder"
```

### Task 2: P2-005 K-line Reconstruction Validator

**Files:**
- Create: `tests/test_p2_kline_validator.py`
- Create: `services/market_ingestion/kline_validator.py`
- Modify: `services/market_ingestion/__init__.py`

**Step 1: Write the failing test**

```python
def test_validator_detects_missing_interval() -> None:
    validator = KlineReconstructionValidator(interval_ms=60_000)
    result = validator.validate(bars)
    assert result.is_valid is False
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p2_kline_validator.py -v`
Expected: FAIL because kline validator module does not exist.

**Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class KlineBar: ...

@dataclass(frozen=True)
class KlineValidationResult: ...

class KlineReconstructionValidator:
    def validate(self, bars: Sequence[KlineBar]) -> KlineValidationResult: ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p2_kline_validator.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_p2_kline_validator.py services/market_ingestion/kline_validator.py services/market_ingestion/__init__.py
git commit -m "feat(ingestion): add kline reconstruction validator"
```

### Task 3: P2-006 Canonical Normalization + Publisher

**Files:**
- Create: `tests/test_p2_canonical_pipeline.py`
- Create: `services/market_ingestion/canonical_pipeline.py`
- Modify: `services/market_ingestion/__init__.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_publish_order_book_delta_to_market_canonical() -> None:
    pipeline = CanonicalNormalizationPipeline(publisher=fake_publisher)
    await pipeline.publish_order_book_delta(delta, mode="MOCK")
    assert fake_publisher.messages[0]["routing_key"] == "market.canonical"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p2_canonical_pipeline.py -v`
Expected: FAIL because canonical pipeline module does not exist.

**Step 3: Write minimal implementation**

```python
class CanonicalPublisher(Protocol):
    async def publish(self, *, routing_key: str, message: Mapping[str, Any]) -> None: ...

class CanonicalNormalizationPipeline:
    def normalize_order_book_delta(self, delta: OrderBookDelta, mode: str) -> dict[str, Any]: ...
    async def publish_order_book_delta(self, delta: OrderBookDelta, mode: str) -> dict[str, Any]: ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_p2_canonical_pipeline.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_p2_canonical_pipeline.py services/market_ingestion/canonical_pipeline.py services/market_ingestion/__init__.py
git commit -m "feat(ingestion): add canonical normalization and publisher pipeline"
```

### Task 4: Docs + Progress Tracker Updates

**Files:**
- Create: `tests/test_p2_integrity_docs.py`
- Modify: `docs/market_ingestion_foundation.md`
- Create: `docs/learning/2026-02-14-p2-integrity-instincts.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Modify: `README.md`

**Step 1: Write the failing test**

```python
def test_readme_mentions_p2_integrity_modules() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "services/market_ingestion/gap_detection.py" in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p2_integrity_docs.py -v`
Expected: FAIL because docs and references are missing.

**Step 3: Write minimal implementation**

- Document module responsibilities and canonical flow with resync and validation gates.
- Add atomic instinct notes aligned with continuous-learning-v2.
- Update `IMPLEMENTATION_PLAN.md`:
  - mark `P2-004`, `P2-005`, `P2-006` as `DONE`
  - append progress ledger + turn update
  - refresh immediate next actions.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_p2_integrity_docs.py docs/market_ingestion_foundation.md docs/learning/2026-02-14-p2-integrity-instincts.md docs/IMPLEMENTATION_PLAN.md README.md
git commit -m "docs: record p2 integrity and canonical pipeline completion"
```
