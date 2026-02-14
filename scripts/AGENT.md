# AGENT.md

## Responsibility

Contains developer and operational utility scripts (validation, maintenance, tooling support).

## Architectural Boundaries

- Scripts assist workflows; they should not embed core service runtime behavior.

## Coding Conventions

- Keep scripts small, explicit, and safe-by-default.
- Fail fast with actionable error output.

## Dependency Rules

- Scripts may depend on repo-local tooling and config contracts.
- Avoid hidden environment assumptions.

## Extension Rules

- New scripts should document input, output, and failure behavior.

## Integration Contracts

- Environment validation scripts must match `.env.example` requirements.

## Testing Expectations

- Add focused tests for script behavior that affects CI or deployment gates.

## Operational Notes

- Prefer idempotent script behavior for repeatable local and CI use.
