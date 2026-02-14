# Continuous Learning v2 Notes - P2 Delivery Batch

Source session: `2026-02-14` (`P2-007`, `P2-008`, `P2-009`)

## Atomic Instincts

```yaml
---
id: write-timeseries-rows-through-protocol
trigger: "when persisting market ingestion artifacts"
confidence: 0.83
domain: "backend-patterns"
source: "session-observation"
---
action: "Persist table-ready rows through protocol adapters instead of binding domain logic to a concrete DB driver."
evidence:
  - "TimescalePersistenceWriters uses a TimeseriesStore protocol with async upsert methods."
```

```yaml
---
id: expose-metrics-as-snapshot-contract
trigger: "when adding ingestion observability"
confidence: 0.81
domain: "observability"
source: "session-observation"
---
action: "Keep in-memory metrics deterministic and expose one stable snapshot payload with counters/lag/rates."
evidence:
  - "MarketPipelineMetrics snapshot includes counters plus lag and rolling rates."
```

```yaml
---
id: replay-determinism-via-stable-digest
trigger: "when validating canonical normalization with fixtures"
confidence: 0.86
domain: "integration-testing"
source: "session-observation"
---
action: "Compare replay runs using digest over deterministic fields only, excluding volatile IDs/timestamps."
evidence:
  - "IngestionIntegrationHarness hashes routing_key/event_type/mode/idempotency_key/payload."
```
