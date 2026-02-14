# Continuous Learning v2 Notes - P4 Execution Metrics and OMS Lifecycle Batch

Source session: `2026-02-14` (`P4-007`, `P4-008`, `P5-001`)

## Atomic Instincts

```yaml
---
id: instrument-mock-and-real-execution-with-snapshot-collectors
trigger: "when execution spans both Python simulation and Go real workers"
confidence: 0.86
domain: "observability"
source: "session-observation"
---
action: "Use in-memory collectors with stable snapshot outputs in both runtimes so latency/failure/throughput can be compared consistently."
evidence:
  - "`SimulationExecutionMetrics.snapshot()` and Go `metrics.Collector.Snapshot()` expose aligned execution telemetry contracts."
```

```yaml
---
id: prove-mode-separation-with-integration-tests
trigger: "when routing isolation is a hard safety requirement"
confidence: 0.88
domain: "integration-testing"
source: "session-observation"
---
action: "Add integration tests that assert mock and real queues/events never leak across mode boundaries."
evidence:
  - "`tests/test_p4_mode_integration.py` verifies queue isolation and mode-specific behavior."
```

```yaml
---
id: encode-order-lifecycle-rules-in-an-explicit-state-machine
trigger: "when OMS status transitions must be deterministic and replay-safe"
confidence: 0.87
domain: "domain-modeling"
source: "session-observation"
---
action: "Represent valid transitions in code and treat invalid transitions as hard errors while allowing idempotent no-op repeats."
evidence:
  - "`services/oms/state_machine.py` defines allowed transitions, terminal states, and strict normalization/validation."
```
