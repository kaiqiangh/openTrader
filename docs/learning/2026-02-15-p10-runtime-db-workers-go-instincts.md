# Continuous Learning - P10 Runtime DB Workers and Go Concrete Adapters (2026-02-15)

## Session Context

- Wired runtime worker startup to fail fast on DB connectivity errors by default.
- Replaced remaining in-memory OMS/news runtime worker state with SQL-backed stores when runtime engine is configured.
- Started `P10-004` by replacing Go noop runtime wiring with concrete RabbitMQ HTTP consumer, HTTP bridge client, and OMS lifecycle publisher hooks.

## Learned Instincts

1. Runtime fail-fast checks should be centralized at process startup.
   - Doing DB connectivity validation in worker entrypoint startup avoids partial startup states where loops run without durable persistence.

2. Runtime state migrations are safer with hybrid wiring.
   - Keep in-memory fallback for deterministic unit tests, but switch to SQL-backed stores automatically when runtime engine is present.

3. Concrete adapter tests should avoid environment-level networking assumptions.
   - HTTP adapter tests are more portable in restricted environments when implemented with mocked `http.RoundTripper` instead of opening local listeners.

4. Bridge success/failure should emit lifecycle events at source.
   - Publishing OMS lifecycle events directly from real execution dispatch path reduces downstream ambiguity and improves observability.

## Follow-Up Candidates

- Finish `P10-004` by validating concrete bridge endpoint behavior inside Docker runtime.
- Expand `P10-002` coverage for runtime-critical RabbitMQ ack/nack and DLQ behavior.
- Advance `P10-005`/`P10-006` compose-first runtime boot and end-to-end validation gates.
