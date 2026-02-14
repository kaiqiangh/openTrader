# P9-001 to P9-003 Validation Design

## Scope

Deliver Phase 9 validation entry checks for:

- `P9-001`: end-to-end MOCK flow (`market -> agent -> simulation -> OMS -> portfolio snapshot`).
- `P9-002`: end-to-end REAL flow (`market -> agent -> execution.intent.real -> reconciliation`).
- `P9-003`: strict mode-isolation evidence that MOCK runtime never uses live order endpoints.

## Constraints

- Prefer runnable integration tests over new production runtime abstractions.
- Reuse existing runtime workers and engines (`runtime_pipeline`, `simulation_execution`, OMS engines).
- Keep REAL validation environment-safe (no actual exchange dispatch), while still validating real-path contracts.

## Candidate Approaches

1. Add pure unit tests per module only.
   - Pros: fast and simple.
   - Cons: does not satisfy Phase 9 end-to-end validation intent.
2. Add Python integration harness tests using in-memory broker + scripted adapters and compose OMS engines.
   - Pros: verifies multi-service behavior with deterministic, repeatable tests and no external dependencies.
   - Cons: REAL execution bridge is emulated, not external live exchange traffic.
3. Run dockerized cross-language full-stack tests for every run.
   - Pros: closest to production.
   - Cons: heavy and brittle for CI/local iteration; unnecessary for this gate.

## Selected Design

Choose approach 2.

- Build `P9-001` integration test on top of:
  - `MarketIngestionRuntimeWorker`
  - `AgentOrchestratorRuntimeWorker`
  - `RuntimeIntegrationGate`
  - `SimulationExecutionWorker`
  - `FillReconciliationEngine`
  - `PositionEngine`
  - `PortfolioSnapshotEngine`
- Build `P9-002` integration test by:
  - validating `execution.intent.real` envelope emitted by orchestrator,
  - emulating real execution lifecycle artifacts,
  - validating fallback-aware reconciliation behavior.
- Build `P9-003` compliance test by:
  - instrumenting market clients to detect order-write attempts,
  - asserting full MOCK pipeline emits only mock intents and never touches real queue or order endpoints.

## Evidence and Documentation

- Add dedicated `tests/test_p9_*.py` suite.
- Add Phase 9 validation runtime evidence doc.
- Update `docs/IMPLEMENTATION_PLAN.md` statuses and next actions.
- Update `README.md` to include P9 validation test references.
