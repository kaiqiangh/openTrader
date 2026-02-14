# Continuous Learning v2 Notes - P7 Governance/Replay/Dashboard Batch

Source session: `2026-02-14` (`P7-004`, `P7-005`, `P7-006`)

## Atomic Instincts

```yaml
---
id: aggregate-llm-governance-in-state-layer
trigger: "when exposing llm usage and breach history endpoints"
confidence: 0.87
domain: "backend-patterns"
source: "session-observation"
---
action: "Keep governance aggregation in state/service adapters and let routers only map filters and response schemas."
evidence:
  - "`services/api/state.py` computes usage and breach aggregates from `llm_call_records` and `llm_quota_limits`."
  - "`services/api/routers/governance.py` forwards query filters and serializes typed responses."
```

```yaml
---
id: map-replay-not-found-to-http-404
trigger: "when wrapping replay service contracts into fastapi routes"
confidence: 0.9
domain: "api-design"
source: "session-observation"
---
action: "Translate domain-level replay missing errors into explicit `404` responses and keep successful responses deterministic."
evidence:
  - "`services/api/routers/replay.py` catches `DecisionReplayNotFoundError` for replay request and decision lookup paths."
  - "`tests/test_p7_api_governance_replay_dashboard.py` verifies unknown decision IDs return `404`."
```

```yaml
---
id: ship-dashboard-shell-as-html-read-model
trigger: "when phase requires dashboard baseline before full ui build"
confidence: 0.82
domain: "delivery-strategy"
source: "session-observation"
---
action: "Provide lightweight server-rendered HTML pages that link core status/governance/replay views to unblock operator workflows early."
evidence:
  - "`services/api/routers/dashboard.py` exposes `/dashboard`, `/dashboard/status`, `/dashboard/governance`, and `/dashboard/replay` HTML routes."
```
