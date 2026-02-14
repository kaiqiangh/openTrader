# Continuous Learning - P7 Notification Observability (2026-02-14)

## Session Context

- Implemented `P7-016` notification observability across runtime collector, API telemetry endpoints, and dashboard hooks.

## Learned Instincts

1. Add observability in pipeline stage boundaries, not only at end-state.
   - Capturing policy and dispatch spans separately made filtered vs delivery failures explicit.

2. Use suppression deltas, not cumulative counters, when deriving per-event telemetry.
   - Reading policy router counts before/after routing prevents overcount inflation in shared in-memory routers.

3. Dashboard hooks should verify both route shell markers and API path presence in shipped JS.
   - This catches regressions where backend exists but frontend wiring is missing.

4. Keep telemetry contracts explicit in API schemas.
   - Pydantic response models for totals/logs/traces reduced accidental shape drift.

## Follow-Up Candidates

- Wire collector output to centralized metrics/logging exporters in Phase 8 (`P8-001`..`P8-004`).
- Add DLQ age/depth API metrics once queue-backed notification worker is deployed (`P7-018`).
