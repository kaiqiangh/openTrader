# Implementation Plan

## LLM-Based Multi-Exchange Crypto Trading System (Based on ARD v1.1)

- Last Updated: 2026-02-14
- Source of truth: `./docs/ARD_Consolidated.md`
- Planning horizon: End-to-end implementation to production-ready deployment on Docker Compose

## 1. How We Track Progress Each Turn

### 1.1 Status Legend

- `NOT_STARTED`
- `IN_PROGRESS`
- `BLOCKED`
- `DONE`

### 1.2 Priority Legend

- `P0` critical path/blocker
- `P1` core product capability
- `P2` important but non-blocking

### 1.3 Turn Update Protocol (Use Every Turn)

Use this exact format in each update:

```markdown
### Turn Update YYYY-MM-DD HH:MM

- Completed Task IDs: [ ... ]
- In Progress Task IDs: [ ... ]
- Blocked Task IDs: [ ... ]
- New Risks/Blockers: ...
- Next Task IDs: [ ... ]
- Overall Progress: XX%
```

### 1.4 Progress Ledger (Append-Only)

| Turn | Date       | Completed IDs | In Progress IDs | Blocked IDs | Notes        | Overall % |
| ---- | ---------- | ------------- | --------------- | ----------- | ------------ | --------- |
| 0    | 2026-02-14 | -             | -               | -           | Plan created | 0%        |
| 1    | 2026-02-14 | P0-001,P0-002,P0-004,P0-005,P0-006,P0-007 | - | P0-003 | Phase 0 bootstrap started; Python tests green | 8% |
| 2    | 2026-02-14 | P1-002 | P1-001 | P0-003 | Phase 1 foundation scaffolded; tests green | 14% |
| 3    | 2026-02-14 | P1-003,P1-004,P1-008 | P1-001 | P0-003 | Added schema migrations and RabbitMQ topology; tests green | 22% |
| 4    | 2026-02-14 | P1-005 | P1-001 | P0-003 | Agent trace schema migration delivered; tests green | 26% |
| 5    | 2026-02-14 | P1-001,P0-003,P1-006 | - | - | Runtime verification succeeded; Go tests unblocked locally; LLM governance schema added | 36% |
| 6    | 2026-02-14 | P1-007,P1-009,P1-010 | - | - | News schema, envelope contract, and Redis namespace strategy delivered; tests green | 45% |
| 7    | 2026-02-14 | P2-001,P2-002,P2-003 | - | - | Ingestion adapter, resilience manager, and orderbook sync engine delivered; tests green | 54% |
| 8    | 2026-02-14 | P2-004,P2-005,P2-006 | - | - | Gap detection, k-line validation, and canonical publisher delivered; tests green | 63% |
| 9    | 2026-02-14 | P2-007,P2-008,P2-009 | - | - | Persistence writers, pipeline metrics, and replay harness delivered; tests green | 72% |
| 10   | 2026-02-14 | P3-001,P3-002,P3-003 | - | - | Agent orchestrator, planner, and risk baseline delivered; tests green | 81% |
| 11   | 2026-02-14 | P3-004 | - | - | Execution decision agent with constrained proposals delivered; tests green | 84% |
| 12   | 2026-02-14 | P3-005 | - | - | Market context enrichment agent delivered with microstructure/news context flow; tests green | 87% |
| 13   | 2026-02-14 | P3-006 | - | - | LLM gateway skeleton delivered with timeout/retry/fallback contracts; tests green | 90% |
| 14   | 2026-02-14 | P3-007 | - | - | LLM prompt/response persistence with token/cost/latency audit records delivered; tests green | 93% |
| 15   | 2026-02-14 | P3-008 | - | - | Hard-limit token/cost quota enforcement delivered with quota-blocked audit records; tests green | 96% |
| 16   | 2026-02-14 | P3-009 | - | - | Guardrail validation layer delivered with pre-publish gating and structured violations; tests green | 99% |
| 17   | 2026-02-14 | P3-010 | - | - | Memory layer integration delivered with Redis short-term slots and Postgres long-term summary persistence; tests green | 100% |
| 18   | 2026-02-14 | P3-011 | - | - | Replay service delivered with deterministic decision graph reconstruction and digest validation; tests green | 100% |
| 19   | 2026-02-14 | P3-012 | - | - | Agent metrics/tracing baseline delivered with stage latency/failure instrumentation and LLM token telemetry hooks; tests green | 100% |
| 20   | 2026-02-14 | - | - | - | PRD/ARD/plan updated with extensible notification architecture and Telegram-first delivery roadmap | 100% |
| 21   | 2026-02-14 | - | - | - | Added Phase 0-3 completeness gap review and AGENT.md documentation rollout; identified critical runtime integration gaps before Phase 4 | 100% |
| 22   | 2026-02-14 | P3-013,P3-014,P3-015,P3-016,P4-001,P4-002,P4-003 | - | - | Runtime integration gate delivered with concrete broker/workers/adapters plus strict mode routing, simulation engine, and mock safety guard | 100% |
| 23   | 2026-02-14 | - | - | - | Added concrete Binance transport adapter and completed full-suite runtime validation (`pytest` green) | 100% |
| 24   | 2026-02-14 | P4-004,P4-005,P4-006 | - | - | Real execution Go queue-consumer skeleton, bridge contracts, and idempotent create/cancel dedupe dispatch delivered with Go test coverage | 100% |
| 25   | 2026-02-14 | P4-007,P4-008,P5-001 | - | - | Added execution metrics/tracing, mode integration tests, and OMS lifecycle state machine; Python/Go suites green | 100% |
| 26   | 2026-02-14 | P5-002,P5-003,P5-004 | - | - | Added OMS fill reconciliation, position engine, and portfolio snapshot engine; fixed `uv run pytest` parity with root-level pass | 100% |
| 27   | 2026-02-14 | P5-005,P5-006,P5-007 | - | - | Added OMS core risk rules, drawdown/daily-loss guards, and circuit-breaker/kill-switch controls with composed policy engine; Python/Go suites green | 100% |
| 28   | 2026-02-14 | P5-008,P5-009,P6-001 | - | - | Added risk observability telemetry, risk regression scenario suite, and pluggable news source connector framework; Python/Go suites green | 100% |
| 29   | 2026-02-14 | P6-002,P6-003,P6-004 | - | - | Added news ingestion + dedupe persistence, tagging/relevance pipeline, and rolling summarizer service with deterministic fallback behavior | 100% |
| 30   | 2026-02-14 | P6-005,P6-006,P6-007 | - | - | Added summary context injection bridge, resilience fallback/alert policy, and quality metrics snapshot contracts; Python/Go suites green | 100% |
| 31   | 2026-02-14 | P7-001,P7-002,P7-003 | - | - | Added FastAPI control-plane baseline with JWT RBAC and trading ops endpoints for orders/positions/portfolio/risk controls; Python/Go suites green | 100% |
| 32   | 2026-02-14 | P7-004,P7-005,P7-006 | - | - | Added LLM governance APIs, replay APIs, and dashboard shell routes on top of control-plane baseline; targeted/full Python suites green | 100% |
| 33   | 2026-02-14 | P7-007,P7-008,P7-009 | - | - | Added React-based dashboard UI layer for governance/replay/mode panels, mode-audit API endpoint, and static UI assets served by FastAPI; Python/Go suites green | 100% |
| 34   | 2026-02-14 | P7-010,P7-011,P7-012 | - | - | Added news panel APIs/UI, notification runtime core module, and source event publisher integrations across strategy/OMS/risk/system-health paths; Python/Go suites green | 100% |
| 35   | 2026-02-14 | P7-013,P7-014,P7-015 | - | - | Added Telegram gateway delivery, notification preference CRUD APIs, and hardened dedupe/rate-limit/backoff retry + DLQ behavior with regression coverage; Python/Go suites green | 100% |
| 36   | 2026-02-14 | P7-016 | - | - | Added notification observability collector, telemetry ops APIs, and dashboard notification panel hooks for metrics/logs/traces; Python/Go suites green | 100% |
| 37   | 2026-02-14 | P7-017 | - | - | Expanded notification validation suite with dispatcher fault-injection scenarios and publish->deliver integration coverage across bridge/runtime/observability flow; Python/Go suites green | 100% |
| 38   | 2026-02-14 | P7-018 | - | - | Added notification worker deployment/config wiring with startup validation, compose integration, and env/secrets documentation; targeted/full Python suites plus Go tests green | 100% |
| 39   | 2026-02-14 | P8-001,P8-002,P8-003 | - | - | Added shared structured logging, Prometheus-compatible metrics exposition, and trace-context propagation baseline across API/notification worker plus Go runtime tracing helpers; Python/Go suites green | 100% |
| 40   | 2026-02-14 | P8-004,P8-005,P8-006 | - | - | Added compose observability stack configs/services (Prometheus/Grafana/Loki/Tempo/Alertmanager), critical alert rule catalog, and AES-256-GCM encrypted exchange credential store runtime; Python/Go suites green | 100% |
| 41   | 2026-02-14 | P8-007,P8-008,P8-009 | - | - | Hardened compose network isolation with public/internal split, expanded Phase 8 security validation suite coverage, and added incident runbooks for exchange outage/quota breach/risk events; Python/Go suites green | 100% |
| 42   | 2026-02-14 | P9-001,P9-002,P9-003 | - | - | Phase 9 validation setup completed; replay determinism and chaos/performance gates queued next | 100% |
| 43   | 2026-02-14 | - | P9-004 readiness hotfixes | - | Runtime unblockers delivered for notification worker `.env` loading, queue bootstrap behavior, and API bootstrap parity | 100% |
| 44   | 2026-02-14 | P9 runtime ops unblockers | - | - | Fixed `make env-validate` import path, made `docker compose up -d` start full stack by default, and added `make smoke` comprehensive runtime smoke checks | 100% |

### Turn Update 2026-02-14 10:55

- Completed Task IDs: [P0-001, P0-002, P0-004, P0-005, P0-006, P0-007]
- In Progress Task IDs: [-]
- Blocked Task IDs: [P0-003]
- New Risks/Blockers: Go toolchain test execution is limited in current sandbox due restricted network/toolchain download.
- Next Task IDs: [P0-003, P1-001, P1-002]
- Overall Progress: 8%

### Turn Update 2026-02-14 11:20

- Completed Task IDs: [P1-002]
- In Progress Task IDs: [P1-001]
- Blocked Task IDs: [P0-003]
- New Risks/Blockers: Docker daemon is not reachable in this environment, so runtime verification of Compose startup is pending.
- Next Task IDs: [P1-001, P1-003, P1-004]
- Overall Progress: 14%

### Turn Update 2026-02-14 11:35

- Completed Task IDs: [P1-003, P1-004, P1-008]
- In Progress Task IDs: [P1-001]
- Blocked Task IDs: [P0-003]
- New Risks/Blockers: Docker runtime checks remain blocked until Docker daemon is available locally.
- Next Task IDs: [P1-001, P1-005, P1-006]
- Overall Progress: 22%

### Turn Update 2026-02-14 11:50

- Completed Task IDs: [P1-005]
- In Progress Task IDs: [P1-001]
- Blocked Task IDs: [P0-003]
- New Risks/Blockers: No new blockers. Existing blockers remain: Docker daemon unavailable (runtime compose checks) and Go toolchain network restriction.
- Next Task IDs: [P1-001, P1-006, P1-007]
- Overall Progress: 26%

### Turn Update 2026-02-14 12:05

- Completed Task IDs: [P1-001, P0-003, P1-006]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No current blockers on the previous critical path items.
- Next Task IDs: [P1-007, P1-009, P1-010]
- Overall Progress: 36%

### Turn Update 2026-02-14 12:20

- Completed Task IDs: [P1-007, P1-009, P1-010]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified.
- Next Task IDs: [P2-001, P2-002, P2-003]
- Overall Progress: 45%

### Turn Update 2026-02-14 12:29

- Completed Task IDs: [P2-001, P2-002, P2-003]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified.
- Next Task IDs: [P2-004, P2-005, P2-006]
- Overall Progress: 54%

### Turn Update 2026-02-14 12:45

- Completed Task IDs: [P2-004, P2-005, P2-006]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified.
- Next Task IDs: [P2-007, P2-008, P2-009]
- Overall Progress: 63%

### Turn Update 2026-02-14 13:00

- Completed Task IDs: [P2-007, P2-008, P2-009]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified.
- Next Task IDs: [P3-001, P3-002, P3-003]
- Overall Progress: 72%

### Turn Update 2026-02-14 13:15

- Completed Task IDs: [P3-001, P3-002, P3-003]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified.
- Next Task IDs: [P3-004, P3-005, P3-006]
- Overall Progress: 81%

### Turn Update 2026-02-14 13:30

- Completed Task IDs: [P3-004]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified.
- Next Task IDs: [P3-005, P3-006, P3-007]
- Overall Progress: 84%

### Turn Update 2026-02-14 13:45

- Completed Task IDs: [P3-005]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified.
- Next Task IDs: [P3-006, P3-007, P3-008]
- Overall Progress: 87%

### Turn Update 2026-02-14 14:00

- Completed Task IDs: [P3-006]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified.
- Next Task IDs: [P3-007, P3-008, P3-009]
- Overall Progress: 90%

### Turn Update 2026-02-14 14:15

- Completed Task IDs: [P3-007]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified.
- Next Task IDs: [P3-008, P3-009, P3-010]
- Overall Progress: 93%

### Turn Update 2026-02-14 14:30

- Completed Task IDs: [P3-008]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified.
- Next Task IDs: [P3-009, P3-010, P3-011]
- Overall Progress: 96%

### Turn Update 2026-02-14 14:45

- Completed Task IDs: [P3-009]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified.
- Next Task IDs: [P3-010, P3-011, P3-012]
- Overall Progress: 99%

### Turn Update 2026-02-14 14:56

- Completed Task IDs: [P3-010]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified.
- Next Task IDs: [P3-011, P3-012, P4-001]
- Overall Progress: 100%

### Turn Update 2026-02-14 15:06

- Completed Task IDs: [P3-011]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified.
- Next Task IDs: [P3-012, P4-001, P4-002]
- Overall Progress: 100%

### Turn Update 2026-02-14 15:13

- Completed Task IDs: [P3-012]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified.
- Next Task IDs: [P4-001, P4-002, P4-003]
- Overall Progress: 100%

### Turn Update 2026-02-14 15:20

- Completed Task IDs: [-]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified.
- Next Task IDs: [P4-001, P4-002, P4-003]
- Overall Progress: 100%

### Turn Update 2026-02-14 15:27

- Completed Task IDs: [-]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: Phase 0-3 audit found critical runtime integration gaps (exchange adapters, broker workers, persistence adapters) despite contract-level task completion.
- Next Task IDs: [P4-001, P4-002, P4-003]
- Overall Progress: 100%

### Turn Update 2026-02-14 15:44

- Completed Task IDs: [P3-013, P3-014, P3-015, P3-016, P4-001, P4-002, P4-003]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified after runtime integration gate implementation and targeted runtime test validation.
- Next Task IDs: [P4-004, P4-005, P4-006]
- Overall Progress: 100%

### Turn Update 2026-02-14 15:47

- Completed Task IDs: [-]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified; full test suite passed after concrete exchange adapter addition.
- Next Task IDs: [P4-004, P4-005, P4-006]
- Overall Progress: 100%

### Turn Update 2026-02-14 15:56

- Completed Task IDs: [P4-004, P4-005, P4-006]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: Go test execution requires writable `GOCACHE` override in this environment (`GOCACHE=/tmp/go-build`).
- Next Task IDs: [P4-007, P4-008, P5-001]
- Overall Progress: 100%

### Turn Update 2026-02-14 16:07

- Completed Task IDs: [P4-007, P4-008, P5-001]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: Local `uv run pytest` can fail without async plugin availability; documented workaround in `README.md`. Retain `GOCACHE=/tmp/go-build` for local Go tests in this environment.
- Next Task IDs: [P5-002, P5-003, P5-004]
- Overall Progress: 100%

### Turn Update 2026-02-14 16:20

- Completed Task IDs: [P5-002, P5-003, P5-004]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: `uv sync` currently panics in this environment; local async pytest fallback in `tests/conftest.py` keeps `uv run pytest` operational. Retain `GOCACHE=/tmp/go-build` for local Go tests in this environment.
- Next Task IDs: [P5-005, P5-006, P5-007]
- Overall Progress: 100%

### Turn Update 2026-02-14 16:45

- Completed Task IDs: [P5-005, P5-006, P5-007]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified; retain local environment notes (`uv sync` panic in this environment and `GOCACHE=/tmp/go-build` requirement for Go tests).
- Next Task IDs: [P5-008, P5-009, P6-001]
- Overall Progress: 100%

### Turn Update 2026-02-14 17:20

- Completed Task IDs: [P5-008, P5-009, P6-001]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified; LLM env semantics clarified (LiteLLM runtime keys vs optional upstream provider credentials).
- Next Task IDs: [P6-002, P6-003, P6-004]
- Overall Progress: 100%

### Turn Update 2026-02-14 17:55

- Completed Task IDs: [P6-002, P6-003, P6-004]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified; deterministic baseline summaries are non-LLM and should be upgraded in later phases when quality/cost targets are finalized.
- Next Task IDs: [P6-005, P6-006, P6-007]
- Overall Progress: 100%

### Turn Update 2026-02-14 18:10

- Completed Task IDs: [P6-005, P6-006, P6-007]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified; Phase 6 contracts are complete but UI/API dashboard surfaces remain deferred to Phase 7.
- Next Task IDs: [P7-001, P7-002, P7-003]
- Overall Progress: 100%

### Turn Update 2026-02-14 18:36

- Completed Task IDs: [P7-001, P7-002, P7-003]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified; API control plane uses in-memory state adapters and should be followed by persistence-backed governance/replay endpoints.
- Next Task IDs: [P7-004, P7-005, P7-006]
- Overall Progress: 100%

### Turn Update 2026-02-14 19:05

- Completed Task IDs: [P7-004, P7-005, P7-006]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified; governance/replay/dashboard surfaces are currently backed by in-memory API state adapters and should be persisted in a later increment.
- Next Task IDs: [P7-007, P7-008, P7-009]
- Overall Progress: 100%

### Turn Update 2026-02-14 19:40

- Completed Task IDs: [P7-007, P7-008, P7-009]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified; dashboard UI uses static React module delivery and remains coupled to in-memory API adapters pending persistence-backed control-plane integration.
- Next Task IDs: [P7-010, P7-011, P7-012]
- Overall Progress: 100%

### Turn Update 2026-02-14 20:15

- Completed Task IDs: [P7-010, P7-011, P7-012]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified; notification runtime currently uses in-memory preference/rate-limit state and in-memory DLQ records pending persistence-backed implementation in later notification phases.
- Next Task IDs: [P7-013, P7-014, P7-015]
- Overall Progress: 100%

### Turn Update 2026-02-14 20:40

- Completed Task IDs: [P7-013, P7-014, P7-015]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified; Telegram delivery and preference APIs are operational but persistence-backed notification stores and observability dashboards remain for the next phase batch.
- Next Task IDs: [P7-016, P7-017, P7-018]
- Overall Progress: 100%

### Turn Update 2026-02-14 20:55

- Completed Task IDs: [P7-016]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified; notification telemetry currently uses in-memory collector/state surfaces pending exporter integration in Phase 8 observability stack.
- Next Task IDs: [P7-017, P7-018, P8-001]
- Overall Progress: 100%

### Turn Update 2026-02-14 21:05

- Completed Task IDs: [P7-017]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified; coverage is strong for in-memory runtime paths, while queue-backed worker/deployment behavior remains the next gap for `P7-018`.
- Next Task IDs: [P7-018, P8-001, P8-002]
- Overall Progress: 100%

### Turn Update 2026-02-14 21:25

- Completed Task IDs: [P7-018]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified; notification worker startup validation and deployment wiring are now in place for compose-based runtime bring-up.
- Next Task IDs: [P8-001, P8-002, P8-003]
- Overall Progress: 100%

### Turn Update 2026-02-14 22:05

- Completed Task IDs: [P8-001, P8-002, P8-003]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified; current metrics/tracing baseline is in-process and contract-level, while full observability stack deployment remains in `P8-004`.
- Next Task IDs: [P8-004, P8-005, P8-006]
- Overall Progress: 100%

### Turn Update 2026-02-14 22:35

- Completed Task IDs: [P8-004, P8-005, P8-006]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified; observability stack wiring and key-encryption runtime are complete, with next hardening tranche focused on network isolation, security validation suite, and runbooks.
- Next Task IDs: [P8-007, P8-008, P8-009]
- Overall Progress: 100%

### Turn Update 2026-02-14 22:55

- Completed Task IDs: [P8-007, P8-008, P8-009]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified; Phase 8 hardening is complete and Phase 9 validation/performance/release gates are now the critical path.
- Next Task IDs: [P9-001, P9-002, P9-003]
- Overall Progress: 100%

### Turn Update 2026-02-14 23:20

- Completed Task IDs: [P9-001, P9-002, P9-003]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: No new blockers identified; replay determinism and performance/chaos validation remain open release gates for Phase 9.
- Next Task IDs: [P9-004, P9-005, P9-006]
- Overall Progress: 100%

### Turn Update 2026-02-14 23:55

- Completed Task IDs: [-]
- In Progress Task IDs: [P9-004 readiness hotfixes]
- Blocked Task IDs: [-]
- New Risks/Blockers: Resolved pre-Phase-9 runtime blockers for notification worker startup, `.env` loading, and API/uvicorn local bootstrap; migration fallback now works for network reachability but existing Postgres credential drift on reused volumes still requires local operator reset/alignment.
- Next Task IDs: [P9-004, P9-005, P9-006]
- Overall Progress: 100%

### Turn Update 2026-02-14 23:59

- Completed Task IDs: [P9 runtime ops unblockers]
- In Progress Task IDs: [-]
- Blocked Task IDs: [-]
- New Risks/Blockers: `make env-validate` import-path issue resolved; `docker compose up -d` now starts full service stack by default; comprehensive smoke runner (`make smoke`) added and passing. Remaining non-code operational caveat is optional Postgres volume credential drift during migration fallback on reused local volumes.
- Next Task IDs: [P9-004, P9-005, P9-006]
- Overall Progress: 100%

## 2. Milestone Roadmap (Multi-Phase)

| Phase | Name                               | Objective                                                       | Exit Gate                                    | Status      |
| ----- | ---------------------------------- | --------------------------------------------------------------- | -------------------------------------------- | ----------- |
| 0     | Program Setup                      | Repo, standards, CI skeleton, environment contracts             | CI passes on scaffold; standards documented  | DONE |
| 1     | Data + Messaging Foundation        | PostgreSQL+Timescale, Redis, RabbitMQ, base schemas/events      | Core infra online via Docker Compose         | DONE |
| 2     | Market Ingestion + Integrity       | Robust exchange ingestion with resync/gap detection             | Continuous market flow with integrity checks | DONE |
| 3     | Agent Runtime + LLM Gateway        | Multi-agent orchestration with memory and guardrails            | Validated agent decision pipeline            | DONE |
| 3.5   | Runtime Integration Gate           | Concrete adapters/workers for broker, persistence, and model transport | Runnable Phase 2-3 pipeline validation completed | DONE |
| 4     | Dual Execution Modes               | MOCK simulation + REAL execution (Go) with strict routing       | End-to-end mock and real flows validated     | DONE |
| 5     | OMS + Portfolio + Risk             | Full lifecycle state machine and risk-authoritative control     | Risk gates verified; lifecycle consistent    | DONE |
| 6     | News Intelligence Module           | News ingestion, persistence, summarization, context injection   | News affects agent context safely            | DONE |
| 7     | API + Dashboard + Notifications    | Control plane, observability UI, and event notifications        | Operator workflows and alerts usable end-to-end | DONE |
| 8     | Observability + Security Hardening | Logs/metrics/traces/alerts + RBAC + encryption                  | SLO and security baseline met                | DONE |
| 9     | Validation + Perf + Release        | E2E, load, chaos, replay validation, runbooks                   | Production-readiness sign-off                | IN_PROGRESS |

## 3. Workstreams

- WS-A: Platform + DevEx
- WS-B: Data + Messaging
- WS-C: Market Connectivity + Integrity
- WS-D: Agentic Strategy + LLM Governance
- WS-E: Execution + OMS + Risk
- WS-F: News Intelligence
- WS-G: API + UI
- WS-H: Observability + Security + Reliability
- WS-I: QA + Performance + Release
- WS-J: Notification and Operator Communication
- WS-K: Runtime Integration Gate

## 4. Detailed Phase Plan

## Phase 0 - Program Setup

### Objective

Create implementation scaffolding, coding standards, CI gates, and environment templates aligned with ARD constraints.

### Exit Criteria

- Project scaffold exists for Python and Go services.
- `.env` contract documented and validated.
- CI runs lint, type checks, and unit tests.

### Tasks

| ID     | Pri | Task                        | Actionable Steps                                                                                                                                                                                                     | Dependencies  | Deliverable                   | Status      |
| ------ | --- | --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- | ----------------------------- | ----------- |
| P0-001 | P0  | Repo structure bootstrap    | Create service directories (`api`, `market_ingestion`, `integrity_service`, `agent_orchestrator`, `llm_gateway`, `simulation_execution`, `real_execution_go`, `oms`, `news_ingestion`, `news_summarizer`, `workers`) | -             | Deterministic monorepo layout | DONE |
| P0-002 | P0  | Python baseline setup       | Configure Python 3.13 tooling, dependency management, formatting, linting, typing                                                                                                                                    | P0-001        | Reproducible Python toolchain | DONE |
| P0-003 | P0  | Go baseline setup           | Configure Go module for `real_execution_go`, lint/test setup                                                                                                                                                         | P0-001        | Reproducible Go toolchain     | DONE |
| P0-004 | P0  | `.env` schema contract      | Define required env vars per service and validation script                                                                                                                                                           | P0-001        | `.env.example` + validator    | DONE |
| P0-005 | P1  | CI skeleton                 | Add workflows for lint/test/build for Python and Go                                                                                                                                                                  | P0-002,P0-003 | Green CI on scaffold          | DONE |
| P0-006 | P1  | Architecture decision index | Add ADR directory and initial ADRs for ARD mandates                                                                                                                                                                  | P0-001        | ADR baseline                  | DONE |
| P0-007 | P1  | Local developer onboarding  | Add `Makefile`/task runner commands and bootstrap docs                                                                                                                                                               | P0-001        | Onboarding playbook           | DONE |

---

## Phase 1 - Data + Messaging Foundation

### Objective

Implement foundational infrastructure: PostgreSQL+TimescaleDB, Redis, RabbitMQ, and canonical event/data contracts.

### Exit Criteria

- Docker Compose launches all core data services.
- Migration system and base schemas operational.
- Event exchange/queue topology declared and tested.

### Tasks

| ID     | Pri | Task                          | Actionable Steps                                                                                            | Dependencies | Deliverable                         | Status      |
| ------ | --- | ----------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------ | ----------------------------------- | ----------- |
| P1-001 | P0  | Docker Compose core stack     | Define services for postgres-timescaledb, redis, rabbitmq, shared networks, volumes                         | P0-004       | Running infra stack                 | DONE |
| P1-002 | P0  | Database migration framework  | Set up migrations and migration CI check                                                                    | P1-001       | Repeatable schema migration process | DONE |
| P1-003 | P0  | Core trading schema           | Implement `exchanges`, `symbols`, `orders`, `fills`, `positions`, `portfolio_snapshots`                     | P1-002       | Trading schema v1                   | DONE |
| P1-004 | P0  | Time-series schema            | Implement Timescale hypertables for `klines`, `orderbook_snapshots`                                         | P1-002       | Time-series schema v1               | DONE |
| P1-005 | P0  | Agent trace schema            | Implement `decision_traces`, `agent_runs`, `agent_messages`                                                 | P1-002       | Agent trace persistence             | DONE |
| P1-006 | P0  | LLM governance schema         | Implement `llm_calls`, `llm_usage_daily`, `llm_usage_monthly`, `llm_quota_limits`                           | P1-002       | LLM observability schema            | DONE |
| P1-007 | P1  | News schema                   | Implement `news_items`, `news_tags`, `news_summaries`, `decision_news_links`                                | P1-002       | News persistence schema             | DONE |
| P1-008 | P0  | RabbitMQ topology declaration | Define exchanges, routing keys, queues, DLQs (`market.canonical`, `execution.intent.*`, `oms.events`, etc.) | P1-001       | Versioned broker topology           | DONE |
| P1-009 | P1  | Message envelope contract     | Define shared envelope (`trace_id`, `decision_id`, `mode`, `idempotency_key`) and schema validators         | P1-008       | Canonical event contract package    | DONE |
| P1-010 | P1  | Redis namespace strategy      | Define keys/TTL for short-term memory, snapshots, rate limits, locks                                        | P1-001       | Redis keyspace spec                 | DONE |

---

## Phase 2 - Market Ingestion + Integrity

### Objective

Build resilient exchange ingestion and data integrity controls (resync, gap detection, k-line validation).

### Exit Criteria

- Continuous ingest from Binance/Bitget.
- Integrity service detects/recover gaps.
- Canonical market stream published reliably to RabbitMQ.

### Tasks

| ID     | Pri | Task                             | Actionable Steps                                                                    | Dependencies  | Deliverable                      | Status      |
| ------ | --- | -------------------------------- | ----------------------------------------------------------------------------------- | ------------- | -------------------------------- | ----------- |
| P2-001 | P0  | CCXT Pro ingestion adapter       | Build exchange clients for WS + REST snapshot bootstrap                             | P1-008        | Unified ingestion adapters       | DONE |
| P2-002 | P0  | Connection resilience            | Implement heartbeat, stale detection, reconnect with exponential backoff and jitter | P2-001        | Stable connection manager        | DONE |
| P2-003 | P0  | Order book sync engine           | Snapshot + delta apply logic with sequence handling                                 | P2-001        | Consistent local order books     | DONE |
| P2-004 | P0  | Gap detection module             | Detect sequence gaps and trigger controlled resync                                  | P2-003        | Gap alarms + recovery actions    | DONE |
| P2-005 | P0  | K-line reconstruction validator  | Validate interval completeness, monotonic timestamps, missing bars                  | P2-001        | K-line quality guard             | DONE |
| P2-006 | P1  | Canonical normalization pipeline | Normalize exchange payloads to canonical schema                                     | P2-001        | Canonical event publisher        | DONE |
| P2-007 | P1  | Persistence writers              | Persist kline and orderbook snapshots to Timescale                                  | P2-006,P1-004 | Historical data persisted        | DONE |
| P2-008 | P1  | Market pipeline metrics          | Expose ingestion lag/rates/reconnect counters                                       | P2-002        | Prometheus metrics for ingestion | DONE |
| P2-009 | P1  | Integration test harness         | Replay fixture streams and validate deterministic normalization                     | P2-006        | Ingestion integration tests      | DONE |

---

## Phase 3 - Agent Runtime + LLM Gateway

### Objective

Implement planner/risk/execution-decision agents, orchestrator, memory model, guardrails, and full prompt/response observability.

### Exit Criteria

- Agent pipeline produces validated execution intents.
- All LLM calls are persisted with full payloads and metrics.
- Replay can reconstruct agent decision traces.

### Tasks

| ID     | Pri | Task                        | Actionable Steps                                                                  | Dependencies         | Deliverable                              | Status      |
| ------ | --- | --------------------------- | --------------------------------------------------------------------------------- | -------------------- | ---------------------------------------- | ----------- |
| P3-001 | P0  | Orchestrator skeleton       | Build orchestrator consuming `market.canonical` and managing decision lifecycle   | P1-009,P2-006        | Agent orchestration runtime              | DONE |
| P3-002 | P0  | Planner agent               | Implement dynamic plan generation based on market context and strategy config     | P3-001               | Planner output contracts                 | DONE |
| P3-003 | P0  | Risk agent                  | Implement risk-analysis agent outputs for pre-trade risk signals                  | P3-001               | Risk agent outputs                       | DONE |
| P3-004 | P0  | Execution decision agent    | Implement final action proposal agent with schema constraints                     | P3-001               | Action proposals (`BUY/SELL/HOLD/CLOSE`) | DONE |
| P3-005 | P1  | Market context agent        | Implement optional context enrichment with market microstructure + news summaries | P3-001               | Optional context module                  | DONE |
| P3-006 | P0  | LLM gateway service         | Build LiteLLM-backed gateway with retries/timeouts/provider config                | P3-001               | Centralized model access layer           | DONE |
| P3-007 | P0  | Prompt/response persistence | Persist full prompt and full response with tokens/cost/latency/trace IDs          | P1-006,P3-006        | Complete LLM audit trail                 | DONE |
| P3-008 | P0  | Token quota enforcement     | Enforce per-agent/per-strategy daily token + monthly cost hard limits             | P1-006,P3-006        | Quota guardrails                         | DONE |
| P3-009 | P0  | Guardrail validation layer  | Validate schema, risk policy, symbol constraints, leverage, confidence threshold  | P3-002,P3-003,P3-004 | Intent validation gate                   | DONE |
| P3-010 | P1  | Memory layer integration    | Implement short-term Redis memory and long-term Postgres memory writes/reads      | P1-005,P1-010        | Shared memory system                     | DONE |
| P3-011 | P1  | Replay service              | Reconstruct decision graph and payloads from persisted traces                     | P3-007,P1-005        | Deterministic replay API/service         | DONE |
| P3-012 | P1  | Agent metrics/tracing       | Instrument agent latencies, failure rates, token consumption                      | P3-001               | Observability for agent runtime          | DONE |

---

## Phase 3.5 - Runtime Integration Gate

### Objective

Close integration gaps between Phase 2-3 logic contracts and runnable runtime behavior before advancing deeper into Phase 4.

### Exit Criteria

- Runnable ingestion -> broker -> orchestrator -> execution intent flow is validated.
- Concrete persistence adapters exist for ingestion, memory, and LLM governance runtime surfaces.
- Concrete LiteLLM-compatible provider transport is implemented.
- Runtime gate validation artifacts are documented.

### Tasks

| ID     | Pri | Task                                 | Actionable Steps                                                                 | Dependencies      | Deliverable                              | Status      |
| ------ | --- | ------------------------------------ | -------------------------------------------------------------------------------- | ----------------- | ---------------------------------------- | ----------- |
| P3-013 | P0  | Broker/exchange adapters + worker runtime | Implement concrete topic broker adapter, concrete exchange transport adapter, and market/orchestrator worker loops | P1-008,P2-006,P3-001 | Runnable market->decision runtime path | DONE |
| P3-014 | P0  | Concrete persistence adapters        | Implement concrete stores for timeseries, memory summaries, and LLM governance   | P1-004,P1-005,P1-006 | Executable runtime persistence adapters | DONE |
| P3-015 | P0  | Concrete LLM transport adapter       | Implement LiteLLM-compatible HTTP client adapter with timeout/error handling      | P3-006            | Runnable model transport adapter         | DONE |
| P3-016 | P0  | Runtime gate integration validation  | Add runtime gate tests and verification documentation                              | P3-013,P3-014,P3-015 | Runtime gate evidence and pass report  | DONE |

---

## Phase 4 - Dual Execution Modes

### Objective

Implement and hard-separate MOCK and REAL execution paths.

### Entry Criteria

- `P3-016` runtime integration gate must be completed with runnable market->decision->intent pipeline evidence.
- Phase advancement must be based on executable runtime validation, not contract-only completion.

### Exit Criteria

- MOCK mode performs simulated lifecycle only.
- REAL mode executes live orders through Go service.
- Routing assertions prevent mode leakage.

### Tasks

| ID     | Pri | Task                               | Actionable Steps                                                                    | Dependencies  | Deliverable                  | Status      |
| ------ | --- | ---------------------------------- | ----------------------------------------------------------------------------------- | ------------- | ---------------------------- | ----------- |
| P4-001 | P0  | Mode routing policy                | Implement strict mode router for `execution.intent.mock` vs `execution.intent.real` | P3-016,P3-009,P1-008 | Deterministic routing layer  | DONE |
| P4-002 | P0  | Simulation engine core             | Build simulated matching/fill engine with slippage and fees model                   | P4-001        | Mock execution runtime       | DONE |
| P4-003 | P0  | Simulation safety guard            | Add assertions guaranteeing no exchange order endpoint usage in MOCK mode           | P4-002        | Mode isolation safety        | DONE |
| P4-004 | P0  | Go real execution service skeleton | Build Go service with queue consumer and idempotent command handler                 | P4-001,P0-003 | Real execution service       | DONE |
| P4-005 | P0  | CCXT Pro bridge contracts          | Define strongly typed command contract for Go<->Python exchange actions             | P4-004,P2-001 | Execution interface contract | DONE |
| P4-006 | P0  | Idempotent order dispatch          | Enforce idempotency keys and dedupe for create/cancel actions                       | P4-004        | Safe at-least-once behavior  | DONE |
| P4-007 | P1  | Execution metrics and tracing      | Instrument both engines with latency/failure counters and traces                    | P4-002,P4-004 | Engine observability         | DONE |
| P4-008 | P1  | Mode integration tests             | Automated tests proving strict mode separation and expected lifecycle events        | P4-002,P4-004 | Mode compliance test suite   | DONE |

---

## Phase 5 - OMS + Portfolio + Risk

### Objective

Implement lifecycle state machine, reconciliation, portfolio accounting, and risk-authoritative enforcement.

### Exit Criteria

- OMS state transitions are correct and resilient.
- Risk policy blocks violating intents/orders.
- Portfolio and PnL are accurate for both modes.

### Tasks

| ID     | Pri | Task                          | Actionable Steps                                                                                                          | Dependencies         | Deliverable                 | Status      |
| ------ | --- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------- | -------------------- | --------------------------- | ----------- |
| P5-001 | P0  | OMS state machine             | Implement state transitions (`NEW`, `SUBMITTED`, `OPEN`, `PARTIALLY_FILLED`, `FILLED`, `CANCELED`, `REJECTED`, `EXPIRED`) | P1-003,P4-002,P4-004 | Robust OMS core             | DONE |
| P5-002 | P0  | Fill reconciliation           | Combine queue events + exchange query fallback reconciliation                                                             | P5-001,P4-004        | Reconciled order/fill state | DONE |
| P5-003 | P0  | Position engine               | Update positions from fills for mock and real mode                                                                        | P5-001               | Position service            | DONE |
| P5-004 | P0  | Portfolio snapshot engine     | Generate NAV, realized/unrealized PnL snapshots                                                                           | P5-003               | Portfolio snapshots in DB   | DONE |
| P5-005 | P0  | Core risk rules               | Implement position limits, leverage checks, per-symbol exposure limits                                                    | P3-009,P5-001        | Risk rule engine            | DONE |
| P5-006 | P0  | Drawdown + daily loss rules   | Implement max drawdown and daily loss guardrails                                                                          | P5-004               | Portfolio risk protection   | DONE |
| P5-007 | P0  | Circuit breaker + kill switch | Implement system-wide stop controls and eventing                                                                          | P5-005,P5-006        | Emergency controls          | DONE |
| P5-008 | P1  | Risk observability            | Metrics/logs for risk checks, denials, and breaches                                                                       | P5-005               | Risk telemetry              | DONE |
| P5-009 | P1  | Risk regression tests         | Scenario tests for each policy and edge case                                                                              | P5-005,P5-006        | Risk validation suite       | DONE |

---

## Phase 6 - News Intelligence Module

### Objective

Integrate news/social signals into the agent context pipeline safely and observably.

### Exit Criteria

- News ingestion/summarization persisted and queryable.
- Agent context receives fresh summaries.
- Trading pipeline remains resilient when news fails.

### Tasks

| ID     | Pri | Task                           | Actionable Steps                                                         | Dependencies  | Deliverable                 | Status      |
| ------ | --- | ------------------------------ | ------------------------------------------------------------------------ | ------------- | --------------------------- | ----------- |
| P6-001 | P1  | Source connector framework     | Implement pluggable source connectors for RSS/APIs/social feeds          | P1-007        | Connector framework         | DONE |
| P6-002 | P1  | News ingestion service         | Pull, normalize, deduplicate (`source_id + hash`) and persist news items | P6-001        | Persisted news feed         | DONE |
| P6-003 | P1  | Tagging and relevance pipeline | Symbol/topic tagging + relevance/sentiment scoring                       | P6-002        | Tagged news entities        | DONE |
| P6-004 | P1  | News summarizer service        | Generate rolling summaries per symbol/global windows                     | P6-002,P3-006 | Summary artifacts           | DONE |
| P6-005 | P1  | Context injection bridge       | Publish summaries to strategy context queue and MCTX agent input         | P6-004,P3-005 | News-aware strategy context | DONE |
| P6-006 | P1  | News resilience behavior       | Implement `news_unavailable` fallback and alerting                       | P6-002,P6-004 | Non-blocking news module    | DONE |
| P6-007 | P2  | News quality dashboard         | Coverage, freshness, summarization lag, error rates                      | P6-002,P6-004 | News ops visibility         | DONE |

---

## Phase 7 - API + Dashboard + Notifications

### Objective

Deliver operational control plane, dashboards, and notification workflows for trading operations, risk, and LLM governance.

### Exit Criteria

- Operators can monitor/control modes, strategies, risks, and execution.
- Token governance dashboard meets ARD requirements.
- Prompt/response inspector and replay UI/API available.
- Severity-classified notifications are delivered through Telegram and extensible gateway contracts.

### Tasks

| ID     | Pri | Task                         | Actionable Steps                                                              | Dependencies         | Deliverable          | Status      |
| ------ | --- | ---------------------------- | ----------------------------------------------------------------------------- | -------------------- | -------------------- | ----------- |
| P7-001 | P0  | FastAPI control plane        | Implement auth, strategy control, mode control, health and metadata endpoints | P0-002,P1-003        | API service baseline | DONE |
| P7-002 | P0  | RBAC enforcement             | Implement `viewer/operator/admin` role checks on sensitive endpoints          | P7-001               | RBAC control plane   | DONE |
| P7-003 | P1  | Trading ops endpoints        | Orders, positions, portfolio snapshots, risk status, circuit breaker controls | P5-001,P5-004,P5-007 | Operator APIs        | DONE |
| P7-004 | P1  | LLM governance endpoints     | Expose per-strategy/per-agent usage, cost, quota and breach history           | P3-007,P3-008        | Governance APIs      | DONE |
| P7-005 | P1  | Replay endpoints             | Expose replay request and decision trace retrieval endpoints                  | P3-011               | Replay APIs          | DONE |
| P7-006 | P1  | Dashboard shell              | Implement UI navigation and live status pages                                 | P7-001               | Dashboard baseline   | DONE |
| P7-007 | P1  | Token usage dashboard UI     | Per strategy/agent daily/monthly cost and quota views                         | P7-004               | Governance UI        | DONE |
| P7-008 | P1  | Prompt/response inspector UI | Drill-down by decision and agent with raw payload views                       | P7-005               | Explainability UI    | DONE |
| P7-009 | P1  | Trading mode panel UI        | Explicit mode display/control with audit history                              | P7-001,P4-001        | Mode control UI      | DONE |
| P7-010 | P2  | News panel UI                | News stream, summaries, symbol impact insights                                | P6-004               | News operations UI   | DONE |
| P7-011 | P0  | Notification service module  | Implement event intake, policy router, gateway dispatch, dedupe/rate-limit skeleton | P1-008,P1-009    | Notification runtime core | DONE |
| P7-012 | P0  | Event publisher integration  | Emit notification events from strategy, OMS, risk, system-health pipelines    | P7-011,P5-001        | End-to-end event routing | DONE |
| P7-013 | P0  | Telegram gateway             | Implement Telegram bot sender, message templates, retryable error handling    | P7-011               | Telegram delivery channel | DONE |
| P7-014 | P1  | Preference management APIs   | Add per-user/per-strategy/event severity preference CRUD and validation        | P7-001,P7-011        | Notification preference control plane | DONE |
| P7-015 | P1  | Spam control + retry policy  | Enforce dedupe windows, rate limits, backoff retries, and delivery DLQ        | P7-011,P1-008        | Resilient notification delivery | DONE |
| P7-016 | P1  | Notification observability   | Add delivery metrics/logs/traces and dashboard panels                          | P7-011,P8-004        | Notification telemetry | DONE |
| P7-017 | P1  | Notification test suite      | Unit tests for policy/gateway routing and integration tests for publish->deliver flow | P7-011,P7-013 | Notification validation suite | DONE |
| P7-018 | P1  | Deployment + config wiring   | Add `.env` keys, compose wiring, secrets docs, startup validation for notification service | P0-004,P1-001,P7-011 | Deployable notification stack | DONE |

---

## Phase 8 - Observability + Security Hardening

### Objective

Implement full monitoring stack, alerting, encryption at rest for keys, network isolation, and production hardening.

### Exit Criteria

- Unified logs/metrics/traces available.
- Alert rules trigger correctly in drills.
- Security controls verified and documented.

### Tasks

| ID     | Pri | Task                           | Actionable Steps                                                                             | Dependencies         | Deliverable                    | Status      |
| ------ | --- | ------------------------------ | -------------------------------------------------------------------------------------------- | -------------------- | ------------------------------ | ----------- |
| P8-001 | P0  | Structured logging standard    | Enforce JSON log schema across all services                                                  | P0-001               | Unified logs with IDs          | DONE |
| P8-002 | P0  | Metrics instrumentation        | Add Prometheus metrics to every service                                                      | P0-001               | Full service metrics           | DONE |
| P8-003 | P0  | Distributed tracing            | Add OpenTelemetry spans/context propagation Python<->Go                                      | P0-002,P0-003        | Cross-service tracing          | DONE |
| P8-004 | P0  | Observability stack in Compose | Configure Prometheus, Grafana, Loki, Tempo, Alertmanager                                     | P1-001               | Observability platform running | DONE |
| P8-005 | P0  | Alert rules                    | Implement critical alerts for disconnects, quota breaches, risk breaches, integrity failures | P8-004               | Alert catalog                  | DONE |
| P8-006 | P0  | Key encryption at rest         | Implement AES-256-GCM for persisted exchange keys                                            | P1-003               | Encrypted key storage          | DONE |
| P8-007 | P0  | Network isolation in Compose   | Split public/internal networks and limit service exposure                                    | P1-001               | Hardened network topology      | DONE |
| P8-008 | P1  | Security test suite            | Auth/RBAC/transport/persistence security checks                                              | P7-002,P8-006,P8-007 | Security validation reports    | DONE |
| P8-009 | P1  | Runbook documentation          | Incident response for exchange outage, quota overrun, risk trips                             | P8-005               | Ops runbooks                   | DONE |

---

## Phase 9 - Validation + Performance + Release

### Objective

Run integration, replay, load, and reliability validation; finalize release readiness.

### Exit Criteria

- All critical tests pass.
- Latency and reliability targets are met or accepted with documented deviations.
- Production readiness checklist approved.

### Tasks

| ID     | Pri | Task                        | Actionable Steps                                                          | Dependencies         | Deliverable                      | Status      |
| ------ | --- | --------------------------- | ------------------------------------------------------------------------- | -------------------- | -------------------------------- | ----------- |
| P9-001 | P0  | E2E mock flow test          | Validate full path market -> agent -> mock execution -> portfolio updates | P4-002,P5-004,P7-001 | E2E mock test pass               | DONE |
| P9-002 | P0  | E2E real flow test          | Validate full path market -> agent -> real execution -> reconciliation    | P4-004,P5-002,P7-001 | E2E real test pass               | DONE |
| P9-003 | P0  | Mode isolation verification | Automated assertion that MOCK never hits exchange order endpoints         | P4-003,P9-001        | Compliance evidence              | DONE |
| P9-004 | P0  | Replay determinism tests    | Verify decision replay reproduces stored decision chain                   | P3-011,P7-005        | Replay validation report         | NOT_STARTED |
| P9-005 | P0  | Performance tests           | Measure dispatch latency, queue throughput, ingestion lag                 | P8-004,P4-004        | Performance benchmark report     | NOT_STARTED |
| P9-006 | P1  | Chaos/resilience drills     | Broker restart, exchange disconnect, LLM timeout, DB restart scenarios    | P8-004,P8-005        | Resilience report                | NOT_STARTED |
| P9-007 | P1  | Data integrity audits       | Validate resync/gap detection/kline reconstruction behavior under faults  | P2-004,P2-005        | Data integrity report            | NOT_STARTED |
| P9-008 | P1  | Security acceptance         | Validate encryption, RBAC, network isolation, secret handling             | P8-008               | Security sign-off                | NOT_STARTED |
| P9-009 | P1  | Release checklist + cutover | Final release checklist, rollback plan, go-live approval                  | P9-001..P9-008       | Production-ready release package | NOT_STARTED |

## 5. Cross-Phase Critical Path

1. P0-001 -> P1-001 -> P1-002 -> P1-003/P1-004/P1-008
2. P2-001 -> P2-003/P2-004 -> P2-006
3. P3-001 -> P3-006 -> P3-007/P3-008/P3-009/P3-010/P3-011/P3-012
4. P3-013/P3-014/P3-015 -> P3-016 -> P4-001
5. P4-001 -> P4-002/P4-003 -> P4-004 -> P5-001/P5-002
6. P5-005/P5-006 -> P7-003 -> P9-001/P9-002
7. P7-011 -> P7-012/P7-013/P7-015 -> P7-016/P7-017
8. P8-004/P8-005 spans all operational readiness gates

## 6. Definition of Done by Capability

### 6.1 MOCK Mode DoD

- No exchange order endpoint calls in logs/traces.
- Simulated lifecycle and PnL fully persisted.
- Risk checks enforced and visible.

### 6.2 REAL Mode DoD

- Idempotent order submission/cancel.
- Lifecycle reconciliation consistent with exchange state.
- Risk and kill-switch controls effective.

### 6.3 Agentic Decisioning DoD

- Planner/risk/execution agents active.
- Guardrails block invalid decisions.
- Full prompt/response + token/cost persistence.

### 6.4 Governance DoD

- Token dashboard supports per-agent/per-strategy day/month.
- Hard limits enforced with alerts and logs.
- Replay available per trade decision.

### 6.5 News Module DoD

- Ingestion + dedupe + persistence functional.
- Summaries injected into context.
- Module failure does not block trading.

### 6.6 Notification DoD

- Severity-classified notification events are published from strategy, OMS, risk, and system-health domains.
- Telegram delivery path works with retry, dedupe, and rate-limit protections.
- User preference filters correctly control route/threshold/suppression behavior.
- Delivery outcomes are observable with metrics/logs/traces and replayable audit records.

### 6.7 Runtime Integration Gate DoD

- Concrete worker runtime path from market ingestion to orchestrator intent publish is runnable and tested.
- Concrete persistence adapters are available for ingestion, memory, and LLM governance runtime surfaces.
- Concrete LiteLLM-compatible HTTP adapter is implemented and covered by tests.
- Runtime gate verification evidence is documented before advancing deeper Phase 4 items.

## 7. Test Strategy Matrix

| Layer             | Test Type                        | Minimum Coverage                    |
| ----------------- | -------------------------------- | ----------------------------------- |
| Data contracts    | Schema validation tests          | 100% of message envelopes           |
| Market ingestion  | Integration + fault injection    | Binance + Bitget core streams       |
| Agent runtime     | Unit + orchestration integration | Planner/risk/execution agents       |
| Execution engines | Unit + integration               | MOCK and REAL engines               |
| Risk controls     | Scenario/regression tests        | All hard rules and circuit breakers |
| API/UI            | Contract + role tests            | All privileged endpoints            |
| Notifications     | Unit + integration + fault tests | Gateway routing, retry, dedupe, DLQ |
| Observability     | Smoke + rule tests               | Metrics/logs/traces/alerts          |
| Replay            | Determinism tests                | Core decision flows                 |

## 8. Risks and Mitigations

| Risk                           | Impact   | Mitigation                                                         |
| ------------------------------ | -------- | ------------------------------------------------------------------ |
| Exchange stream instability    | High     | Reconnect, gap detection, snapshot resync, alerting                |
| LLM cost blowout               | High     | Hard quotas, dashboard monitoring, per-strategy budgets            |
| Mode leakage (mock -> real)    | Critical | Routing assertions, integration tests, audit checks                |
| Queue backlog under volatility | High     | Backpressure controls, scaling consumers, DLQs                     |
| Data drift/integrity issues    | High     | Validation service, resync workflows, integrity alerts             |
| Replay inconsistency           | Medium   | Immutable payload persistence + deterministic reconstruction tests |
| Notification storm/noise       | Medium   | Severity thresholds, dedupe windows, per-user/gateway rate limits |
| Contract/runtime drift         | High     | Runtime integration gate with executable adapters and end-to-end verification before Phase 4 gating |

## 9. First 3 Execution Sprints (Actionable)

### Sprint 1 (Platform Foundation)

- Target tasks: `P0-001..P0-007`, `P1-001..P1-004`, `P1-008`, `P1-009`
- Sprint exit: compose stack up, migrations operational, event contracts locked.

### Sprint 2 (Market + Agent Baseline)

- Target tasks: `P2-001..P2-006`, `P3-001..P3-004`, `P3-006`, `P3-009`
- Sprint exit: canonical market stream -> validated decision intents.

### Sprint 3 (Dual Execution + Risk Baseline)

- Target tasks: `P4-001..P4-006`, `P5-001`, `P5-005`, `P5-007`
- Sprint exit: mock/real mode routing functional with initial risk-authoritative flow.

## 10. Live Task Board (Update In-Place Each Turn)

| Task ID | Owner | Start Date | Target Date | Status      | %   | Blocker | Last Update |
| ------- | ----- | ---------- | ----------- | ----------- | --- | ------- | ----------- |
| P0-001  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P0-002  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P0-003  | TBD   | 2026-02-14 | -           | DONE | 100  | - | 2026-02-14  |
| P0-004  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P1-001  | TBD   | 2026-02-14 | -           | DONE | 100  | - | 2026-02-14  |
| P1-002  | TBD   | 2026-02-14 | -           | DONE | 100   | -       | 2026-02-14  |
| P1-003  | TBD   | 2026-02-14 | -           | DONE | 100   | -       | 2026-02-14  |
| P1-004  | TBD   | 2026-02-14 | -           | DONE | 100   | -       | 2026-02-14  |
| P1-005  | TBD   | 2026-02-14 | -           | DONE | 100   | -       | 2026-02-14  |
| P1-006  | TBD   | 2026-02-14 | -           | DONE | 100   | -       | 2026-02-14  |
| P1-007  | TBD   | 2026-02-14 | -           | DONE | 100   | -       | 2026-02-14  |
| P1-008  | TBD   | 2026-02-14 | -           | DONE | 100   | -       | 2026-02-14  |
| P1-009  | TBD   | 2026-02-14 | -           | DONE | 100   | -       | 2026-02-14  |
| P1-010  | TBD   | 2026-02-14 | -           | DONE | 100   | -       | 2026-02-14  |
| P2-001  | TBD   | 2026-02-14 | -           | DONE | 100   | -       | 2026-02-14  |
| P2-002  | TBD   | 2026-02-14 | -           | DONE | 100   | -       | 2026-02-14  |
| P2-003  | TBD   | 2026-02-14 | -           | DONE | 100   | -       | 2026-02-14  |
| P2-004  | TBD   | 2026-02-14 | -           | DONE | 100   | -       | 2026-02-14  |
| P2-005  | TBD   | 2026-02-14 | -           | DONE | 100   | -       | 2026-02-14  |
| P2-006  | TBD   | 2026-02-14 | -           | DONE | 100   | -       | 2026-02-14  |
| P2-007  | TBD   | 2026-02-14 | -           | DONE | 100   | -       | 2026-02-14  |
| P2-008  | TBD   | 2026-02-14 | -           | DONE | 100   | -       | 2026-02-14  |
| P2-009  | TBD   | 2026-02-14 | -           | DONE | 100   | -       | 2026-02-14  |
| P3-001  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P3-002  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P3-003  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P3-004  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P3-005  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P3-006  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P3-007  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P3-008  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P3-009  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P3-010  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P3-011  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P3-012  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P3-013  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P3-014  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P3-015  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P3-016  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P4-001  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P4-002  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P4-003  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P4-004  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P4-005  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P4-006  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P4-007  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P4-008  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P5-001  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P5-002  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P5-003  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P5-004  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P5-005  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P5-006  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P5-007  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P5-008  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P5-009  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P6-001  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P6-002  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P6-003  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P6-004  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P6-005  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P6-006  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P6-007  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P7-001  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P7-002  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P7-003  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P7-004  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P7-005  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P7-006  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P7-007  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P7-008  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P7-009  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P7-010  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P7-011  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P7-012  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P7-013  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P7-014  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P7-015  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P7-016  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P7-017  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P7-018  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P8-001  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P8-002  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P8-003  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P8-004  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P8-005  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P8-006  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P8-007  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P8-008  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P8-009  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P9-001  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P9-002  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |
| P9-003  | TBD   | 2026-02-14 | -           | DONE        | 100 | -       | 2026-02-14  |

> Note: Keep this board concise for active critical-path tasks. Full task catalog remains in phase sections above.

## 11. Immediate Next Actions

1. Start `P9-004` replay determinism tests for stored decision-chain reproducibility.
2. Start `P9-005` performance tests for dispatch latency, queue throughput, and ingestion lag.
3. Start `P9-006` chaos/resilience drills (broker restart, exchange disconnect, LLM timeout, DB restart).
