# AGENT.md

## Responsibility

Implements REAL-mode execution worker in Go for live order dispatch and cancellation.

## Architectural Boundaries

- Handles only REAL execution intents.
- Must not process MOCK intents.

## Coding Conventions

- Idiomatic Go, explicit error handling, and context-aware cancellation.
- Keep AMQP/exchange adapters isolated from domain decision logic.

## Dependency Rules

- Consume queue contracts from shared topology and message schema.

## Extension Rules

- New execution commands require idempotency, retry policy, and reconciliation hooks.

## Integration Contracts

- Reads `execution.intent.real`; emits execution result/order lifecycle events for OMS.

## Testing Expectations

- Unit tests for command handling and idempotency.
- Integration tests against broker/exchange adapter mocks.

## Operational Notes

- Graceful shutdown and in-flight command safety are mandatory.
