# AGENT.md

## Responsibility

Owns machine-readable runtime contracts: message schemas, broker topology, and namespace conventions.

## Architectural Boundaries

- This directory defines configuration artifacts only.
- No runtime business logic, client implementations, or service orchestration code.

## Coding Conventions

- Prefer JSON for config artifacts.
- Keep keys explicit and deterministic; avoid implicit defaults in config files.

## Dependency Rules

- Service code may read config artifacts.
- Config files must not depend on service internals.

## Extension Rules

- Any new exchange/queue/namespace addition must include backward-compatibility notes.
- Version topology/schema changes and document migration impact.

## Integration Contracts

- Envelope schema must align with shared validator.
- RabbitMQ topology must map to producer/consumer routing keys.
- Redis namespace definitions must include TTL and key pattern.

## Testing Expectations

- Add tests for schema validity and required key presence.
- Add regression checks when topology or namespace maps change.

## Operational Notes

- Keep config update rollouts atomic with matching code changes.
