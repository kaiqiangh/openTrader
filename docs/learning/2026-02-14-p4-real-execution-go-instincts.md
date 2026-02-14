# Continuous Learning v2 Notes - P4 Real Execution Go Batch

Source session: `2026-02-14` (`P4-004`, `P4-005`, `P4-006`)

## Atomic Instincts

```yaml
---
id: structure-go-execution-service-as-runner-handler-bridge
trigger: "when implementing real-execution workers with external side effects"
confidence: 0.87
domain: "backend-patterns"
source: "session-observation"
---
action: "Split queue consumption, envelope handling, and bridge command contracts into separate packages to keep behavior testable and evolvable."
evidence:
  - "`internal/service/runner.go`, `internal/service/handler.go`, and `internal/bridge/contracts.go` separate responsibilities by layer."
```

```yaml
---
id: bind-ack-nack-policy-to-handler-outcome
trigger: "when consuming execution intents from broker deliveries"
confidence: 0.85
domain: "reliability"
source: "session-observation"
---
action: "Ack only successful dispatches and nack failed handler paths so message semantics match real delivery guarantees."
evidence:
  - "`Runner.Run` acks on success, nacks on handler failure, and tracks those outcomes for runtime visibility."
```

```yaml
---
id: enforce-idempotent-dispatch-keys-before-bridge-calls
trigger: "when create/cancel intents may be retried or duplicated"
confidence: 0.9
domain: "risk-controls"
source: "session-observation"
---
action: "Derive deterministic dispatch keys and gate execution through an idempotency store before invoking exchange bridge commands."
evidence:
  - "`Handler` builds dispatch keys from idempotency key plus operation and guards execution with `idempotency.Store.TryStart`."
```
