# Continuous Learning - P9 E2E Validation Gates (2026-02-14)

## Session Context

- Implemented and validated `P9-001`, `P9-002`, and `P9-003` using deterministic integration tests across runtime workers, execution paths, and OMS engines.

## Learned Instincts

1. End-to-end validation can stay deterministic by composing existing workers with in-memory broker fixtures.
   - This keeps Phase 9 regression checks fast without introducing fragile external dependencies.

2. REAL-path validation benefits from reconciliation fallback scenarios in tests.
   - Queue-only lifecycle events are insufficient; exchange snapshot fallback must be asserted explicitly.

3. Mode isolation evidence should test behavior, not just routing constants.
   - Instrumented exchange clients that fail on order-write calls provide stronger compliance guarantees.

4. Validation milestones need explicit doc gates.
   - A dedicated doc test for status rows and next actions prevents plan drift between turns.

## Follow-Up Candidates

- Add replay determinism fixtures reusing these E2E envelopes for `P9-004`.
- Add latency sampling assertions for queue-to-worker stages in `P9-005`.
