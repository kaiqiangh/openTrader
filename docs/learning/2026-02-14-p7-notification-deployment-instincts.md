# Continuous Learning - P7 Notification Deployment Wiring (2026-02-14)

## Session Context

- Implemented `P7-018` to make notification runtime deployable with startup validation, env contract wiring, and Docker Compose worker integration.

## Learned Instincts

1. Match deployment tests to production event naming.
   - `notify.risk.*` envelopes are canonical for notification bridge output, so severity classification must handle that namespace directly.

2. Startup validation should fail fast on conditional secrets.
   - Validate Telegram secrets only when notifications are enabled and Telegram is the selected gateway.

3. Queue-consumer backend choice should be explicit and typed.
   - A strict `NOTIFY_CONSUMER_BACKEND` contract (`rabbitmq_http` vs `inmemory`) avoids silent misconfiguration during local bring-up.

4. Deployment completion needs docs-gated assertions.
   - Keeping plan status checks in tests enforces synchronized updates across implementation and roadmap documentation.

## Follow-Up Candidates

- Add compose profile smoke tests that exercise RabbitMQ HTTP polling against seeded notification envelopes.
- Add a lightweight Telegram mock endpoint for deterministic integration tests without external network calls.
