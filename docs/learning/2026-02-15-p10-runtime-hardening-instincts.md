# Phase 10 Runtime Hardening Instincts (2026-02-15)

## Context
- Objective: progress `P10-003`, harden `P10-005`, and formalize `P10-006` with runtime evidence.
- Scope: runtime worker persistence, compose startup determinism, and integration gate reliability.

## Instincts Captured

1. Smoke probes must never consume shared production queues
- Signal: runtime gate failed even when bridge path worked because smoke consumed `oms.events.order_updates` concurrently with OMS worker.
- Action: use a dedicated probe queue for smoke (`smoke.oms.events.order_updates`) and keep assertions on event-type output.
- Confidence: high

2. Deterministic compose startup needs schema orchestration, not only container restarts
- Signal: `runtime_worker_market` crashed on missing `orderbook_snapshots` table and `runtime_worker_orchestrator` crashed on unrouted publish while topology/schema boot order raced.
- Action: add a one-shot compose `migrator` dependency and bootstrap topology on orchestrator startup.
- Confidence: high

3. Migration compatibility must handle legacy runtime-created schemas
- Signal: Alembic `20260214_0005` failed on duplicate/incompatible legacy news tables (`UUID` vs `TEXT` keys).
- Action: make migration upgrade idempotent with table/index existence checks and typed fallback for `decision_news_links` when UUID FK compatibility is unavailable.
- Confidence: high

4. Runtime gate should emit machine-readable artifacts even on failure
- Signal: debugging was faster because `artifacts/runtime_integration_gate/latest.json` persisted per-check status despite failures.
- Action: keep report writing unconditional and use overall status for pass/fail.
- Confidence: high

5. Service-up assertions need a stability window, not a single snapshot
- Signal: orchestrator briefly appeared as running, then restart-looped due unrouted strategy lifecycle publishes.
- Action: enforce continuous-running duration in smoke checks and add explicit topology queue/binding for `strategy.decision.#`.
- Confidence: high

## Follow-up Hooks
- Complete `P10-003` by eliminating remaining optional in-memory runtime fallbacks on notification/ops critical paths.
- Complete `P10-007` docs/runbooks with migrator/bootstrap ordering and runtime-gate operational usage.
