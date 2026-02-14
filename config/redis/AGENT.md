# AGENT.md

## Responsibility

Defines Redis keyspace strategy, namespaces, and TTL policies.

## Architectural Boundaries

- Namespace and TTL contract only.
- No read/write implementation code.

## Coding Conventions

- Key patterns must include mode and strategy scope when relevant.
- TTL must be explicit for ephemeral data.

## Dependency Rules

- Services may implement stores using this spec.
- This spec must remain storage-implementation-agnostic.

## Extension Rules

- New namespaces require purpose, key pattern, TTL, and owner service.

## Integration Contracts

- Memory and rate-limit modules should align key naming with this spec.

## Testing Expectations

- Validate key pattern and TTL fields for all namespace entries.

## Operational Notes

- Revisit TTL values when retention, replay, or latency requirements change.
