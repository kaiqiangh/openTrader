# AGENT.md

## Responsibility

Executes MOCK-mode order intents in a deterministic simulation engine.

## Architectural Boundaries

- Only MOCK execution behavior belongs here.
- Must never call live exchange order endpoints.

## Coding Conventions

- Keep pricing/slippage/fee models explicit and configurable.

## Dependency Rules

- Consume `execution.intent.mock` contracts only.

## Extension Rules

- Model changes must document impact on replay determinism and PnL comparability.

## Integration Contracts

- Emit execution and fill events compatible with OMS contracts.

## Testing Expectations

- Strong mode-isolation and deterministic replay tests are mandatory.

## Operational Notes

- Any detected REAL-path call from this module is a release blocker.
