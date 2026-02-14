# Continuous Learning v2 Notes - P2 Ingestion Batch

Source session: `2026-02-14` (`P2-001`, `P2-002`, `P2-003`)

## Atomic Instincts

```yaml
---
id: ingestion-contract-before-runtime
trigger: "when implementing new ingestion pipeline modules"
confidence: 0.8
domain: "backend-contracts"
source: "session-observation"
---
action: "Define snapshot/delta contracts and validation before stream loop logic."
evidence:
  - "P2 adapter tests were written before implementation and required normalized contracts."
```

```yaml
---
id: reconnect-policy-needs-deterministic-tests
trigger: "when building retry/backoff managers"
confidence: 0.8
domain: "resilience"
source: "session-observation"
---
action: "Inject randomness to make jitter behavior deterministic under tests."
evidence:
  - "ConnectionResilienceManager uses configurable random_fn in tests."
```

```yaml
---
id: orderbook-gap-detection-first
trigger: "when implementing order book sequence handling"
confidence: 0.85
domain: "market-data-integrity"
source: "session-observation"
---
action: "Treat forward sequence gaps as hard errors and stale deltas as ignorable."
evidence:
  - "Sync engine raises on gaps and returns False for stale deltas."
```
