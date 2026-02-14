# Continuous Learning v2 Notes - P3 Market Context Batch

Source session: `2026-02-14` (`P3-005`)

## Atomic Instincts

```yaml
---
id: enrich-market-context-before-planning
trigger: "when planner/risk agents need optional microstructure/news context"
confidence: 0.84
domain: "agentic-runtime"
source: "session-observation"
---
action: "Run a dedicated context-enrichment step before planning so downstream agents consume a normalized context contract."
evidence:
  - "AgentOrchestrator now emits agent.decision.context_enriched before planner/risk stages."
```

```yaml
---
id: fallback-news-context-explicitly
trigger: "when optional news payload may be missing"
confidence: 0.82
domain: "resilience"
source: "session-observation"
---
action: "Represent missing news with explicit fallback values (summary, sentiment, source_count) and quality flags instead of implicit null handling."
evidence:
  - "MarketContextAgent returns news_unavailable + has_news=false when payload has no news block."
```

```yaml
---
id: keep-context-quality-deterministic
trigger: "when context quality affects decision trace and replay"
confidence: 0.81
domain: "observability"
source: "session-observation"
---
action: "Emit deterministic context quality metrics (has_orderbook, has_news, context_score) so replay and debugging can reason about degraded inputs."
evidence:
  - "MarketContextOutput includes quality map with deterministic score calculation."
```
