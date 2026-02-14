# AGENT.md

## Architecture Overview

`openTrader` is an event-driven trading platform organized as service modules plus shared contracts.

- Data plane: market ingestion normalizes exchange data and emits canonical events.
- Decision plane: orchestrator runs planner/risk/execution decision flow with guardrails.
- Execution plane: simulation and real execution services consume execution intents.
- Control plane: API/UI, operations tooling, and notification routing.
- Platform plane: Postgres/Timescale, Redis, RabbitMQ, observability, and migrations.

## System Principles

1. Contract-first interfaces before concrete adapters.
2. Event immutability and traceability (`trace_id`, `decision_id`, `idempotency_key`).
3. Explicit mode isolation (`MOCK` vs `REAL`) in every execution path.
4. Risk-authoritative gating before any order action.
5. Idempotent processing for all queue-driven side effects.
6. Prefer deterministic behavior and replayable state transitions.

## Service Interaction Rules

- Cross-service communication must use typed events and versioned schemas.
- Direct service-to-service calls are allowed only for bootstrap/health paths.
- Shared domain contracts live in `/Users/kai/Desktop/openTrader/services/shared/`.
- Business-domain logic stays in its owning service module; do not duplicate domain rules across services.

## Event-Driven Guidelines

- Every emitted event must include envelope metadata and deterministic idempotency keys.
- Producers own payload schema correctness; consumers validate and reject invalid payloads.
- Queue and exchange topology changes must be reflected in `/Users/kai/Desktop/openTrader/config/rabbitmq/topology.json`.
- DLQ behavior is mandatory for non-recoverable consumer failures.

## Observability Standards

- Structured logs only (JSON-ready fields, no ad-hoc plain-text-only diagnostics).
- Include `trace_id`, `decision_id`, `service`, and `mode` when available.
- Metrics must expose throughput, latency, failures, and backlog/retry health.
- Traces must preserve context across queue boundaries and async stage transitions.

## Configuration Standards

- Environment variables are the canonical runtime config boundary.
- `/Users/kai/Desktop/openTrader/.env.example` and `/Users/kai/Desktop/openTrader/scripts/validate_env.py` must be kept in sync.
- No hard-coded credentials, tokens, or endpoint secrets in code.
- Service-specific config keys should be namespaced (for example `LLM_*`, `EXCHANGE_*`, `NOTIFY_*`).

## Security Practices

- Treat all external input as untrusted; validate at boundaries.
- Encrypt secrets at rest where applicable and never log raw secrets.
- Enforce least privilege for service credentials and queue/database access.
- Add audit events for privileged control actions and strategy/risk overrides.

## AI/LLM Integration Principles

- All model traffic goes through `/Users/kai/Desktop/openTrader/services/llm_gateway/`.
- Persist full prompt/response payloads plus usage/cost metadata.
- Quota enforcement is mandatory before provider dispatch.
- Guardrails must validate model-derived actions before execution intent publish.

## Strategy Plugin Standards

- Planner/risk/execution logic must use typed contracts.
- Plugins must be deterministic under equivalent input and config.
- Any new plugin must define validation constraints, failure semantics, and test fixtures.
- Strategy extensions must not bypass centralized risk and guardrail checks.

## Notification Gateway Standards

- Notification routing must be provider-agnostic behind a gateway interface.
- Telegram is initial gateway; future gateways must plug in without core router rewrites.
- Notification policies must support severity (`INFO`, `WARNING`, `CRITICAL`), dedupe, rate limit, and retry/DLQ handling.
- Delivery outcomes must be observable and auditable.

## Dependency Rules

- Keep dependencies directional: shared contracts -> domain services -> API/control layers.
- Avoid cyclic imports across service modules.
- New third-party dependencies require explicit justification and minimal scope.

## Testing Expectations

- New behavior requires unit tests and integration tests at boundary points.
- Queue/database/provider adapters require failure-path tests, not only happy-path tests.
- Mode isolation and risk gates are mandatory regression targets.

## Nested AGENT Template Pattern

Use this structure for directory-level `AGENT.md` files:

```markdown
# AGENT.md

## Responsibility

## Architectural Boundaries

## Coding Conventions

## Dependency Rules

## Extension Rules

## Integration Contracts

## Testing Expectations

## Operational Notes
```

All nested AGENT files should keep this section order and concise, directive style.
