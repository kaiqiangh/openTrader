# Continuous Learning v2 Notes - P7 News + Notification Batch

Source session: `2026-02-14` (`P7-010`, `P7-011`, `P7-012`)

## Atomic Instincts

```yaml
---
id: build-news-dashboard-on-explicit-ops-read-models
trigger: "when adding a new dashboard panel that needs stable data contracts"
confidence: 0.87
domain: "api-design"
source: "session-observation"
---
action: "Expose focused read endpoints first (`/ops/news/items`, `/ops/news/summaries`, `/ops/news/impact`) and keep React view logic as a thin consumer of those APIs."
evidence:
  - "`services/api/routers/ops.py` now serves news panel read endpoints."
  - "`services/api/static/dashboard_app.js` news view uses API-backed `Promise.all` fetches."
```

```yaml
---
id: isolate-notification-runtime-core-from-gateway-implementations
trigger: "when implementing multi-gateway notification architecture"
confidence: 0.9
domain: "backend-patterns"
source: "session-observation"
---
action: "Split notification runtime into `event_intake`, `policy_router`, and `gateway_dispatch` so gateway changes do not alter intake/policy logic."
evidence:
  - "`services/notification_service/` contains bounded runtime components and typed contracts."
```

```yaml
---
id: publish-notification-source-events-at-domain-boundaries
trigger: "when integrating notification emission across strategy/oms/risk/system pipelines"
confidence: 0.84
domain: "event-driven-architecture"
source: "session-observation"
---
action: "Attach notification bridge calls at source boundaries (orchestrator lifecycle publish, simulation order publish, risk observability, runtime worker exceptions) rather than central polling."
evidence:
  - "`services/agent_orchestrator/orchestrator.py` emits notification source events from lifecycle flow."
  - "`services/simulation_execution/worker.py`, `services/oms/risk_observability.py`, and `services/workers/runtime_pipeline.py` emit/collect notification source envelopes."
```
