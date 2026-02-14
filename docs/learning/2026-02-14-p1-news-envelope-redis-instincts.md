# Continuous Learning v2 Notes - P1 News Schema, Envelope, and Redis Batch

Source session: `2026-02-14` (`P1-007`, `P1-009`, `P1-010`)

## Atomic Instincts

```yaml
---
id: ship-news-storage-schema-before-news-runtime-features
trigger: "when starting a new domain pipeline with persistence needs"
confidence: 0.85
domain: "database-design"
source: "session-observation"
---
action: "Land schema contracts for domain entities first so downstream ingestion/tagging/summarization modules target stable tables."
evidence:
  - "`20260214_0005_news_schema.py` defines core `news_items`, `news_tags`, `news_summaries`, and `decision_news_links` tables."
```

```yaml
---
id: enforce-envelope-contracts-with-schema-and-runtime-validator
trigger: "when multiple services publish cross-domain events"
confidence: 0.88
domain: "backend-contracts"
source: "session-observation"
---
action: "Maintain one versioned JSON schema and one runtime validator to keep message envelope guarantees consistent across services."
evidence:
  - "`config/contracts/message_envelope.schema.json` and `services/shared/contracts/message_envelope.py` form the shared contract gate."
```

```yaml
---
id: define-redis-keyspace-and-ttl-policy-explicitly
trigger: "when adding cache/state dependencies across mixed workloads"
confidence: 0.84
domain: "operations"
source: "session-observation"
---
action: "Document namespace conventions, TTL policy, and mode-aware key separation early to prevent cache collisions and drift."
evidence:
  - "`config/redis/namespaces.json` and `docs/redis_namespace_strategy.md` codify key patterns and retention policy."
```
