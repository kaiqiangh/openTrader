# Continuous Learning v2 Notes - P7 Control Plane API Batch

Source session: `2026-02-14` (`P7-001`, `P7-002`, `P7-003`)

## Atomic Instincts

```yaml
---
id: enforce-rbac-at-fastapi-dependency-boundary
trigger: "when adding mutable control-plane endpoints"
confidence: 0.9
domain: "security"
source: "session-observation"
---
action: "Apply role gates as reusable FastAPI dependencies so route handlers stay focused on domain logic and role policy remains centralized."
evidence:
  - "`services/api/auth.py` defines `require_viewer`, `require_operator`, and `require_admin` dependency guards used by control and ops routers."
```

```yaml
---
id: keep-api-handlers-thin-with-state-adapters
trigger: "when exposing existing OMS and risk capabilities through HTTP endpoints"
confidence: 0.86
domain: "backend-patterns"
source: "session-observation"
---
action: "Route handlers should map requests/responses only, while adapter state/services compose domain modules and perform mutations."
evidence:
  - "`services/api/state.py` encapsulates mode, strategy, order/position/snapshot reads, and risk control operations consumed by routers."
```

```yaml
---
id: verify-plan-status-with-phase-specific-doc-tests
trigger: "when marking implementation plan tasks complete"
confidence: 0.84
domain: "quality-gates"
source: "session-observation"
---
action: "Use dedicated doc tests with task-specific regex row checks to prevent false positives when plan contains many DONE rows."
evidence:
  - "`tests/test_p7_api_docs.py` asserts `P7-001..P7-003` rows explicitly match `DONE` in `docs/IMPLEMENTATION_PLAN.md`."
```
