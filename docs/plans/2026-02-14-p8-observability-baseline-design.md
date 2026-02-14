# Phase 8 Observability Baseline Design (P8-001/P8-002/P8-003)

## Scope

Deliver the first production-oriented observability baseline across Python and Go runtime surfaces:

- `P8-001`: structured JSON logging standard
- `P8-002`: Prometheus-compatible metrics instrumentation baseline
- `P8-003`: distributed trace context propagation baseline (Python<->Go contracts)

## Existing State

- Multiple services already keep local in-memory telemetry, but there is no shared observability contract for log schema, metrics export format, or trace-context propagation.
- FastAPI control-plane has no global request observability middleware or Prometheus endpoint.
- Notification worker runtime logs with plain text and has no standardized structured log events.
- Go real-execution service tracks internal counters/spans but does not expose trace context helpers or carry trace IDs in runner span records.

## Goals

1. Provide one shared JSON log schema with required correlation fields.
2. Provide one Prometheus text exposition path for control-plane and worker metrics baselines.
3. Provide one trace context helper contract that works in Python and Go without introducing heavy external dependencies.
4. Keep changes additive and backward-compatible with existing tests/runtime behavior.

## Design Approach

### 1) Shared Python observability runtime module

Add a new shared package under `services/shared/runtime/`:

- `structured_logging.py`
  - `StructuredLogger` for deterministic JSON logs.
  - Log payload fields include:
    - `timestamp`, `level`, `service`, `event`
    - correlation keys: `trace_id`, `decision_id`, `order_id`, `strategy_id`, `mode`
    - optional `context` object for extra fields
- `prometheus.py`
  - lightweight in-process registry with:
    - monotonic counter
    - histogram buckets
  - text exposition renderer compatible with Prometheus scrape format.
- `trace_context.py`
  - generate trace IDs/span IDs
  - parse and compose `traceparent`
  - normalize incoming trace headers and produce response headers for propagation.

### 2) FastAPI integration baseline

- Add middleware in `services/api/app.py`:
  - resolve or generate request trace context
  - write structured request-start/request-finish logs
  - record request counters/latency into shared metrics registry
  - return trace header (`traceparent` and `x-trace-id`) for operator correlation
- Add `/metrics` route in `services/api/routers/system.py` exposing Prometheus text from shared registry.

### 3) Notification worker integration baseline

- Replace startup/run loop plain prints with structured logs.
- Record worker-level queue polling/processed/error counters and processing latency in shared metrics registry.
- Reuse envelope `trace_id` and `decision_id` in logs for correlation continuity from source events.

### 4) Go runtime trace baseline

- Add `internal/tracing/tracecontext.go`:
  - parse/build `traceparent`
  - helper generation for trace/span IDs
- Extend runner metric spans to include `trace_id` + `decision_id` when available.
- Keep existing runner behavior unchanged (ack/nack semantics preserved).

## Validation

- Python tests:
  - log schema assertions
  - API `/metrics` exposition assertions
  - middleware trace header propagation assertions
  - notification worker metrics/logging path assertions
- Go tests:
  - trace context parse/build round-trip
  - runner metric snapshot includes propagated trace/decision IDs

## Risks and Mitigations

- Risk: introducing external dependencies may destabilize current environment.
  - Mitigation: implement minimal internal helpers without new runtime dependencies.
- Risk: log schema drift across services.
  - Mitigation: centralize JSON rendering in shared logger utility and test key presence.
- Risk: over-scoping full observability stack before `P8-004`.
  - Mitigation: keep this phase to contract + instrumentation baseline only; stack wiring remains in `P8-004`.
