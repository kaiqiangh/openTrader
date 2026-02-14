# AGENT.md

## Responsibility

Hosts background worker entrypoints and job processors for queue-driven tasks.

## Architectural Boundaries

- Worker orchestration only; core domain rules stay in service modules.

## Coding Conventions

- Implement explicit startup/shutdown, retry handling, and dead-letter strategy.

## Dependency Rules

- Workers should depend on domain service adapters, not vice versa.

## Extension Rules

- New workers require queue contract, idempotency policy, and observability hooks.

## Integration Contracts

- Queue consumer groups and routing keys must match topology declarations.
- Worker startup must validate env/config contracts before entering processing loops.

## Testing Expectations

- Add consumer integration tests with broker and retry behavior coverage.

## Operational Notes

- Worker concurrency settings must be tunable per environment.
- Compose deployment wiring should include clear dependency health checks for broker-backed workers.
