# Continuous Learning v2 Notes - P2 Integrity and Canonical Batch

Source session: `2026-02-14` (`P2-004`, `P2-005`, `P2-006`)

## Atomic Instincts

```yaml
---
id: classify-sequence-window-before-resync
trigger: "when processing order-book deltas with sequence metadata"
confidence: 0.84
domain: "market-data-integrity"
source: "session-observation"
---
action: "Classify incoming windows as accept/ignore_stale/resync before taking recovery action."
evidence:
  - "GapDetectionModule evaluates sequence windows and emits deterministic actions."
```

```yaml
---
id: validate-kline-structure-before-publish
trigger: "when preparing canonical k-line artifacts"
confidence: 0.82
domain: "data-quality"
source: "session-observation"
---
action: "Run k-line continuity and price-consistency validation before publishing canonical events."
evidence:
  - "KlineReconstructionValidator checks monotonicity, missing intervals, and high/low consistency."
```

```yaml
---
id: envelope-validation-is-a-publish-gate
trigger: "when publishing normalized market events"
confidence: 0.88
domain: "event-contracts"
source: "session-observation"
---
action: "Always validate message envelope fields before broker publish."
evidence:
  - "CanonicalNormalizationPipeline validates envelope via shared contract before publish."
```
