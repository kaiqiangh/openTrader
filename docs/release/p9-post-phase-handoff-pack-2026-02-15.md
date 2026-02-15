# Post-Phase 9 Handoff Pack (2026-02-15)

## Scope

This handoff pack consolidates final production-readiness ownership and operations follow-through after `P9-001..P9-009` completion.

It includes:

- go-live owner matrix,
- hypercare checklist,
- backlog triage table.

## 1. Go-Live Owner Matrix

| Area | Primary Owner | Backup Owner | Approval Required | Cutover Responsibility | Hypercare KPI/Signal | Channel |
| ---- | ------------- | ------------ | ----------------- | ---------------------- | -------------------- | ------- |
| API + Control Plane | `TBD` | `TBD` | Engineering Lead | API startup, auth checks, `/metrics` validation | 5xx error rate, auth failures | `#ot-ops-war-room` |
| Market Ingestion + Integrity | `TBD` | `TBD` | Trading Platform Lead | feed continuity, resync integrity checks | reconnect spikes, gap/resync alerts | `#ot-ops-war-room` |
| Execution + OMS/Risk | `TBD` | `TBD` | Risk Owner | mode isolation, lifecycle/reconciliation checks | order failure rate, risk trip frequency | `#ot-ops-war-room` |
| Notification Runtime | `TBD` | `TBD` | Operations Lead | worker health, delivery success/rate limits | failed deliveries, retry/DLQ growth | `#ot-ops-war-room` |
| Observability + Security | `TBD` | `TBD` | Security Owner | alert routes, dashboard health, secret policy checks | alert ingest lag, security auth anomalies | `#ot-ops-war-room` |
| Database + Migrations | `TBD` | `TBD` | Database Owner | migration verification and rollback readiness | migration failures, connection stability | `#ot-ops-war-room` |
| Release Commander | `TBD` | `TBD` | Exec/Program Sponsor | go/no-go call, timeline control, rollback trigger | gate completion and incident thresholds | `#ot-ops-war-room` |

## 2. Hypercare Checklist (T+0 to T+24h)

| Window | Check | Command/Signal | Pass Criteria | Owner | Status |
| ------ | ----- | -------------- | ------------- | ----- | ------ |
| T-30m | Preflight gate | `uv run ruff check .` + `uv run pytest -q` | both pass | `TBD` | `OPEN` |
| T-20m | Env contract | `make env-validate` | pass | `TBD` | `OPEN` |
| T-15m | Runtime smoke | `make smoke` | pass | `TBD` | `OPEN` |
| T-10m | Service health | `docker compose ps` | required services healthy/running | `TBD` | `OPEN` |
| T+0m | Cutover declaration | war-room announcement | cutover start recorded | `TBD` | `OPEN` |
| T+15m | API control-plane sanity | health + metadata + RBAC checks | no auth/routing regressions | `TBD` | `OPEN` |
| T+30m | Execution integrity | OMS and risk event review | no abnormal failure spikes | `TBD` | `OPEN` |
| T+60m | Notification health | delivery/retry/DLQ metrics review | within expected baseline | `TBD` | `OPEN` |
| T+2h | Replay/integrity sample | run replay and integrity smoke queries | deterministic and consistent | `TBD` | `OPEN` |
| T+4h | Security acceptance spot-check | auth/encryption/network boundaries | no control regression | `TBD` | `OPEN` |
| T+12h | Mid-hypercare review | incident + metric trend review | no unresolved Sev1/Sev2 | `TBD` | `OPEN` |
| T+24h | Hypercare closeout | summary report + sign-off | approved by release commander | `TBD` | `OPEN` |

## 3. Backlog Triage Table

| ID | Priority | Item | Why It Matters | Effort | Proposed Owner | Target Sprint | Acceptance Gate |
| -- | -------- | ---- | -------------- | ------ | -------------- | ------------- | --------------- |
| BL-001 | `P1` | Automate release checklist execution report | reduces manual release risk and audit gaps | `M` | `TBD` | `Next` | CI artifact with gate statuses |
| BL-002 | `P1` | Container-level chaos drills (compose restart/network fault) | extends resilience confidence beyond in-process tests | `M` | `TBD` | `Next` | deterministic chaos playbook + pass criteria |
| BL-003 | `P1` | Benchmark history snapshots and trend diff | prevents silent performance regression | `S` | `TBD` | `Next` | baseline + delta report in CI |
| BL-004 | `P2` | Migration credential-drift diagnostic helper | shortens local/prod DB recovery time | `S` | `TBD` | `Next` | explicit remediation guide + command |
| BL-005 | `P2` | Notification topology bootstrap beyond queue auto-declare | improves first-boot resilience for full routing topology | `M` | `TBD` | `Later` | exchange/queue/binding bootstrap check |
| BL-006 | `P2` | Persistent API control-plane state backend | improves restart resilience and operational consistency | `M` | `TBD` | `Later` | state survives restart with parity tests |
| BL-007 | `P3` | Secret scanning gate in pre-merge pipeline | improves prevention of credential leakage | `S` | `TBD` | `Later` | pre-merge scan with policy fail threshold |

## 4. Handoff Notes

- Use this pack with:
  - `docs/release/p9-release-checklist-2026-02-15.md`
  - `docs/release/p9-cutover-and-rollback-2026-02-15.md`
- Fill all `TBD` owner fields before declaring go-live readiness.
- Track checklist status updates in the operations channel during hypercare.
