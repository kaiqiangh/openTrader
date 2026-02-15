# Phase 10 Cleanup and Doc Alignment Instincts (2026-02-15)

## Context

- Objective: close `P10-003` runtime cleanup and `P10-007` docs/runbook alignment.
- Scope: runtime-critical persistence policy, deterministic integration workflow checks, and operations documentation coherence.

## Instincts Captured

1. Runtime policy must be explicit, not implicit
- Signal: notification worker could still be configured with in-memory consumer in environments intended to be infra-backed.
- Action: enforce `RUNTIME_REQUIRE_DATABASE=true` policy to reject in-memory notification backend on runtime-critical paths.
- Confidence: high

2. Runtime schema drift hides behind green unit tests
- Signal: OMS worker crashed in compose due `runtime_oms_portfolio_snapshots.id` NOT NULL mismatch in Postgres while unit tests still passed.
- Action: persist explicit snapshot IDs in runtime store and validate against compose runtime, not test-only DBs.
- Confidence: high

3. Deterministic E2E checks need queue-pressure controls
- Signal: mocked workflow timed out because `market.canonical` backlog starved deterministic test events.
- Action: pause high-volume producer during deterministic check window, purge runtime/audit queues, then resume producer.
- Confidence: high

4. Envelope contract strictness must be respected in test tooling
- Signal: orchestrator rejected injected events when `trace_id` was not UUID-conformant.
- Action: generate contract-valid UUIDs for `trace_id`/`decision_id` in integration scripts.
- Confidence: high

5. Documentation must describe operationally expected compose states
- Signal: operators interpreted `migrator` one-shot `Exited (0)` as failure.
- Action: runbooks and README now state expected one-shot behavior and required validation commands (`make runtime-gate`, `make mock-workflow`).
- Confidence: high

## Follow-up Hooks

- Promote runtime gate + mocked workflow checks into CI/nightly.
- Continue replacing synthetic runtime connectors with production-grade exchange/news connectors.
- Expand read-only React dashboard data coverage while keeping backend write authority.
