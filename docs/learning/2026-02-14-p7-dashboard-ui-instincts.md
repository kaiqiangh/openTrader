# Continuous Learning v2 Notes - P7 Dashboard UI Layer Batch

Source session: `2026-02-14` (`P7-007`, `P7-008`, `P7-009`)

## Atomic Instincts

```yaml
---
id: serve-react-dashboard-shell-from-fastapi-static-assets
trigger: "when phase requires dashboard UI but repo has no standalone frontend workspace"
confidence: 0.84
domain: "delivery-strategy"
source: "session-observation"
---
action: "Render lightweight HTML shells from FastAPI routes and mount static JS/CSS assets for React-driven panel interactivity."
evidence:
  - "`services/api/app.py` mounts `/static` for dashboard assets."
  - "`services/api/routers/dashboard.py` renders `data-view` shells for home/status/governance/replay/mode pages."
```

```yaml
---
id: parallel-fetch-dashboard-panels
trigger: "when loading independent API datasets in UI panels"
confidence: 0.88
domain: "vercel-react-best-practices"
source: "session-observation"
---
action: "Use `Promise.all` for independent calls (governance usage+breaches, mode+history+strategies) to avoid avoidable client waterfalls."
evidence:
  - "`services/api/static/dashboard_app.js` uses parallel fetches in governance and mode views."
```

```yaml
---
id: expose-mode-audit-history-for-operator-ui
trigger: "when trading mode control UI requires audit-facing context"
confidence: 0.9
domain: "api-design"
source: "session-observation"
---
action: "Add explicit mode-history API contract and persist mode transition events in control-plane state, instead of deriving history implicitly."
evidence:
  - "`services/api/routers/control.py` exposes `GET /control/mode/history`."
  - "`services/api/state.py` stores `ModeAuditRecord` entries on mode changes."
```
