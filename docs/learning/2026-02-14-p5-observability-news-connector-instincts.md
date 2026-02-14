# Continuous Learning v2 Notes - P5 Observability and News Connector Batch

Source session: `2026-02-14` (`P5-008`, `P5-009`, `P6-001`)

## Atomic Instincts

```yaml
---
id: wire-risk-observability-as-an-optional-policy-sink
trigger: "when adding telemetry to critical risk decisions"
confidence: 0.88
domain: "observability"
source: "session-observation"
---
action: "Inject observability via an optional sink interface so policy logic stays deterministic while telemetry remains extensible."
evidence:
  - "`RiskPolicyEngine` accepts `observability_sink`, and `RiskObservabilityCollector` records counters, blocker stats, and structured events."
```

```yaml
---
id: lock-risk-edge-cases-with-regression-scenario-tests
trigger: "when risk rules are changed after baseline implementation"
confidence: 0.86
domain: "integration-testing"
source: "session-observation"
---
action: "Capture boundary and failure-mode scenarios in dedicated regression tests to prevent silent behavior drift in policy evaluation."
evidence:
  - "`tests/test_p5_risk_regression.py` preserves edge-case behavior for limits, exposure reduction, breaker state, and blocker semantics."
```

```yaml
---
id: isolate-news-source-failures-per-connector
trigger: "when ingesting from multiple external news providers"
confidence: 0.89
domain: "resilience"
source: "session-observation"
---
action: "Run connector fetch cycles with per-source fault isolation so one failing provider degrades only itself and not the full cycle."
evidence:
  - "`NewsSourceConnectorFramework.fetch_cycle()` catches connector exceptions and emits degraded source results without aborting the batch."
```
