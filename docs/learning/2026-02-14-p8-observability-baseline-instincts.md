# Continuous Learning - P8 Observability Baseline (2026-02-14)

## Session Context

- Implemented `P8-001`, `P8-002`, and `P8-003` baseline observability contracts across Python API/notification worker and Go real-execution runtime helpers.

## Learned Instincts

1. Centralize observability contracts before stack wiring.
   - Shared logger/metrics/trace helpers reduced per-service drift and made instrumentation changes low-risk.

2. Treat correlation keys as mandatory schema, not optional metadata.
   - Always including `trace_id`, `decision_id`, `order_id`, `strategy_id`, and `mode` kept logs queryable even for partial events.

3. Keep metrics exporter dependency-light at baseline stage.
   - In-process Prometheus text exposition enabled deterministic tests and fast iteration before full `P8-004` stack rollout.

4. Propagate trace context through response headers and worker events.
   - Returning `traceparent` + `x-trace-id` on API responses and using envelope trace IDs in worker logs preserves end-to-end debugging continuity.

5. Extend Go telemetry spans with decision identifiers early.
   - Adding `trace_id`/`decision_id` to runner metrics spans improved cross-language traceability without changing queue-handler contracts.

## Follow-Up Candidates

- Add shared exporters to route in-process metrics/logs/traces to Prometheus/Loki/Tempo in `P8-004`.
- Add integration tests that validate trace continuity from API request to notification delivery and Go execution handler spans.
