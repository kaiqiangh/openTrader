# AGENT.md

## Responsibility

Hosts service modules for ingestion, orchestration, execution, API, and shared contracts.

## Architectural Boundaries

- Each subdirectory is a bounded service/module domain.
- Keep cross-domain coupling through shared contracts and explicit adapters.

## Coding Conventions

- Use typed dataclasses/protocols for boundaries.
- Keep domain logic deterministic and side-effect boundaries explicit.

## Dependency Rules

- Shared contracts may be imported by all services.
- Service-to-service direct imports should be minimized and justified.

## Extension Rules

- New services must define ownership, queue/topic contracts, and persistence boundaries.
- Add `AGENT.md` in each new core service folder.

## Integration Contracts

- Envelope contract and routing keys are mandatory for event exchange.

## Testing Expectations

- Unit tests for domain logic.
- Integration tests for broker, persistence, and provider boundaries.

## Operational Notes

- Every runnable service should eventually include startup, health, and graceful shutdown behavior.
