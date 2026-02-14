# Continuous Learning v2 Notes - Runtime Integration Gate and P4 Foundation Batch

Source session: `2026-02-14` (`P3-013`, `P3-014`, `P3-015`, `P3-016`, `P4-001`, `P4-002`, `P4-003`)

## Atomic Instincts

```yaml
---
id: require-runnable-runtime-gate-before-phase-handoff
trigger: "when architectural contracts are green but runtime integration is unproven"
confidence: 0.89
domain: "integration-testing"
source: "session-observation"
---
action: "Gate phase transitions with a deterministic end-to-end runtime cycle that proves ingestion-to-intent flow actually runs."
evidence:
  - "`services/workers/runtime_pipeline.py` plus `tests/test_runtime_pipeline.py` validate concrete pipeline execution before Phase 4 progression."
```

```yaml
---
id: isolate-storage-and-llm-dependencies-behind-runtime-adapters
trigger: "when moving from mocked contracts to concrete persistence/provider integrations"
confidence: 0.86
domain: "backend-patterns"
source: "session-observation"
---
action: "Introduce adapter modules for DB and provider boundaries so deterministic tests can validate behavior without coupling core orchestration."
evidence:
  - "Concrete adapters were added in `services/market_ingestion/sqlalchemy_store.py`, `services/llm_gateway/sqlalchemy_stores.py`, and `services/llm_gateway/litellm_http_adapter.py`."
```

```yaml
---
id: enforce-mode-isolation-with-router-and-safety-guard
trigger: "when mock and real execution paths coexist"
confidence: 0.9
domain: "risk-controls"
source: "session-observation"
---
action: "Make routing policy and safety checks explicit so MOCK and REAL traffic cannot cross queues or reach forbidden endpoints."
evidence:
  - "`services/simulation_execution/mode_routing.py` and `services/simulation_execution/safety_guard.py` enforce routing and endpoint isolation invariants."
```
