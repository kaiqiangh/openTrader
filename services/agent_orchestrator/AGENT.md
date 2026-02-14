# AGENT.md

## Responsibility

Coordinates planner, risk, execution-decision, guardrail, memory, and lifecycle publishing for market-driven decisions.

## Architectural Boundaries

- Owns decision lifecycle and agent sequencing.
- Must not bypass risk/guardrail checks or execution routing policies.

## Coding Conventions

- Keep stage boundaries explicit for metrics and traceability.
- Preserve deterministic decision outputs for replay compatibility.

## Dependency Rules

- Agent modules may use shared contracts and injected gateway/store interfaces.
- Avoid direct exchange or OMS side effects from orchestrator logic.

## Extension Rules

- New agent stage additions require contract updates, lifecycle event definitions, and tests.

## Integration Contracts

- Consumes canonical market envelopes.
- Emits lifecycle events and execution intents with idempotency keys.

## Testing Expectations

- Scenario tests for approve/reject branches and guardrail failures.
- Replay consistency tests for deterministic digest behavior.

## Operational Notes

- Ensure per-stage latency/failure telemetry remains intact when refactoring flow.
