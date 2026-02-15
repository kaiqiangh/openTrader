# Phase 9 Resilience Drill Evidence (2026-02-15)

## Scope

Validation evidence for `P9-006` fault-injection drills:

- Broker restart (temporary consume failure, then recovery).
- Exchange disconnect (delta polling timeout, then reconnect).
- LLM timeout (primary timeout, fallback provider success).
- DB restart analogue (first persistence failure, retry success).

## Commands Executed

1. `uv run pytest tests/test_p9_chaos_resilience.py -q`
2. `uv run pytest tests/test_p9_validation_docs.py -q`

## Drill Outcomes

1. Broker restart drill:
   - first consume attempt raises `ConnectionError`
   - subsequent run recovers and publishes `FILLED` order lifecycle.
2. Exchange disconnect drill:
   - first market poll raises `TimeoutError`
   - worker emits `notify.system.event` with `system.exchange.connectivity_issue`
   - subsequent poll succeeds and publishes canonical market envelope.
3. LLM timeout drill:
   - primary provider times out under configured timeout budget
   - gateway falls back to secondary provider and returns successful response.
4. DB restart drill:
   - first long-term summary persist raises `ConnectionError`
   - retry persist succeeds and summary is available for subsequent memory reads.

## Outcome

- `tests/test_p9_chaos_resilience.py`: PASS
- `P9-006` is validated and marked complete in `docs/IMPLEMENTATION_PLAN.md`.
