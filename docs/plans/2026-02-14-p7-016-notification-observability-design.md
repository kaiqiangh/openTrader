# Phase 7 Notification Observability Design (P7-016)

## Scope

Implement `P7-016` notification observability and dashboard hooks:

- runtime metrics/log/trace capture for notification processing
- API read endpoints for notification telemetry
- dashboard route and UI panel for operator visibility

## Current Baseline

- Notification runtime supports intake, routing, dispatch, Telegram, dedupe/rate-limit, retry, and DLQ.
- Notification source publishers are wired from strategy/OMS/risk/system paths.
- Dashboard currently has home/status/governance/replay/mode/news panels, but no notification telemetry panel.

## Approaches Considered

### A) API-only synthetic telemetry

- Add static counters in API state without runtime integration.
- Pros: minimal code.
- Cons: does not satisfy runtime observability requirement.

### B) Runtime collector + API state adapter (recommended)

- Add a notification observability collector in `services/notification_service`.
- Integrate collector into `NotificationService`.
- Surface telemetry via API state methods and new `ops` endpoints.
- Add dashboard notifications panel.

### C) Full external observability stack integration now

- Wire Prometheus/OpenTelemetry exporters directly.
- Pros: closer to production.
- Cons: belongs to Phase 8 (`P8-004`), too large for this task.

Recommendation: **B** for deterministic in-process telemetry now, with exporter integration later in Phase 8.

## Design

### 1) Notification runtime observability collector

- Add `services/notification_service/observability.py`:
  - counters: received/filtered/dispatched/delivered/failed/retryable/dlq
  - gateway status counters and retry histogram
  - recent structured logs and recent trace spans
- Structured logs include ARD-required fields:
  - `notification_event_id`, `gateway`, `severity`, `delivery_status`, `attempt`, `trace_id`
- Trace spans capture policy evaluation and gateway dispatch latency/status.

### 2) Service integration

- Extend `NotificationService` with optional observability sink.
- In `process_envelope`, record:
  - event received
  - policy routing outcome (including suppression deltas)
  - dispatch outcomes and DLQ growth

### 3) API + dashboard hooks

- Extend API state with notification telemetry records and list/snapshot helpers.
- Add new `ops` endpoints:
  - `GET /ops/notifications/metrics`
  - `GET /ops/notifications/deliveries`
  - `GET /ops/notifications/traces`
- Add dashboard route:
  - `GET /dashboard/notifications`
- Add React view to fetch metrics + recent deliveries/traces and render operator table/cards.

## Validation Plan

- Unit tests for observability collector snapshot/log/trace semantics.
- Integration test for `NotificationService` observability updates.
- API tests for notification telemetry endpoints and dashboard route marker.
- Full regressions (`pytest`, `ruff`, Go tests).
