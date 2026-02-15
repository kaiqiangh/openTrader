# P9-004 to P9-006 Validation Design

## Scope

Deliver the next Phase 9 validation gates:

- `P9-004`: replay determinism tests that prove stored decision-chain reproduction is stable.
- `P9-005`: performance benchmarks for dispatch latency, queue throughput, and ingestion lag.
- `P9-006`: chaos/resilience drills for broker restart, exchange disconnect, LLM timeout, and DB restart conditions.

## Constraints

- Keep validation deterministic and CI-friendly (no hard dependency on external live services).
- Reuse existing runtime modules where possible (`runtime_pipeline`, replay service, simulation execution, LLM gateway, memory layer).
- Prefer fault injection with explicit assertions over brittle timing-heavy integration.

## Candidate Approaches

1. Compose-only operational drills (Docker restart/network fault scripts).
   - Pros: high realism.
   - Cons: slow, flaky, and hard to make deterministic in CI.
2. Deterministic in-process validation harness (recommended).
   - Pros: repeatable, fast, and maps directly to existing domain contracts.
   - Cons: does not measure host-level/container orchestration behavior.
3. Minimal doc-only completion with no executable validations.
   - Pros: fastest.
   - Cons: does not satisfy Phase 9 gate intent.

## Selected Design

Choose approach 2 and implement three validation suites plus evidence docs:

1. `P9-004` replay determinism:
   - Add integration-level replay tests against `ControlPlaneState` + `DecisionReplayService`.
   - Verify deterministic digest stability across repeated calls.
   - Verify replay output preserves the stored lifecycle chain and canonical ordering for runs/messages/LLM calls.

2. `P9-005` performance benchmarks:
   - Add deterministic benchmark tests that collect:
     - simulation execution dispatch latency distribution,
     - in-memory broker throughput,
     - market ingestion lag derived from canonical envelope timestamps.
   - Persist benchmark evidence in runtime docs.

3. `P9-006` chaos/resilience drills:
   - Add fault-injection scenarios for:
     - broker temporary unavailability with recovery,
     - exchange disconnect then reconnect,
     - LLM primary timeout with fallback provider success,
     - long-term memory persistence failure then retry success (DB restart analogue).
   - Capture drill commands and outcomes in runtime docs.

## Artifacts

- Tests:
  - `tests/test_p9_replay_determinism.py`
  - `tests/test_p9_performance_benchmarks.py`
  - `tests/test_p9_chaos_resilience.py`
  - update `tests/test_p9_validation_docs.py`
- Runtime evidence:
  - `docs/runtime/p9-replay-determinism-2026-02-15.md`
  - `docs/runtime/p9-performance-benchmark-2026-02-15.md`
  - `docs/runtime/p9-resilience-drills-2026-02-15.md`
- Planning and learning:
  - `docs/plans/2026-02-15-p9-004-p9-006-validation-implementation.md`
  - `docs/learning/2026-02-15-p9-004-p9-006-instincts.md`
- Progress and operator docs:
  - `docs/IMPLEMENTATION_PLAN.md`
  - `README.md`
