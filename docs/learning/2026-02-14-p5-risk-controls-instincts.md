# Continuous Learning v2 Notes - P5 Risk Controls Batch

Source session: `2026-02-14` (`P5-005`, `P5-006`, `P5-007`)

## Atomic Instincts

```yaml
---
id: compose-risk-policy-from-rules-guards-and-controls
trigger: "when deciding whether an order can be dispatched"
confidence: 0.9
domain: "risk-controls"
source: "session-observation"
---
action: "Evaluate core risk rules, portfolio guards, and emergency controls in one policy engine so allow/deny logic stays centralized."
evidence:
  - "`RiskPolicyEngine` composes core rule checks, drawdown/daily-loss guards, and control-plane gates into one decision."
```

```yaml
---
id: return-explainable-denials-with-deduped-blockers
trigger: "when multiple risk layers can block the same order"
confidence: 0.87
domain: "backend-contracts"
source: "session-observation"
---
action: "Emit structured deny reasons with deterministic deduplication so operators and tests can trace a single authoritative blocker set."
evidence:
  - "`RiskPolicyDecision.blocked_by` is merged via `_merge_blocked()` to preserve order and avoid duplicate blocker names."
```

```yaml
---
id: treat-kill-switch-and-circuit-breaker-as-event-streams
trigger: "when emergency controls must be auditable and operable"
confidence: 0.86
domain: "operations"
source: "session-observation"
---
action: "Model control actions as state plus emitted events so trip/reset and operator actions remain observable and replayable."
evidence:
  - "`RiskControlPlane` tracks kill-switch/circuit-breaker state and emits structured events such as `risk.kill_switch.enabled` and `risk.circuit_breaker.tripped`."
```
