# AGENT.md

## Responsibility

Provides centralized LLM request orchestration: provider routing, retry/timeout, persistence hooks, and quota enforcement.

## Architectural Boundaries

- Owns model provider dispatch contracts and governance boundaries.
- Must not contain trading strategy logic.

## Coding Conventions

- Keep provider-independent request/response models.
- Normalize usage/cost metrics consistently.

## Dependency Rules

- Callers interact through gateway contracts only.
- Provider clients and stores should be injected adapters.

## Extension Rules

- New provider integrations must implement timeout/retry and consistent usage extraction.
- Quota policy extensions require explicit hard-limit behavior docs.

## Integration Contracts

- Persists immutable call records (success, failure, quota-blocked).
- Exposes metrics sink hooks for runtime telemetry.

## Testing Expectations

- Include timeout, retry, fallback, and quota-block regression tests.
- Add adapter integration tests when concrete providers are wired.

## Operational Notes

- Provider outages should degrade with controlled fallback, not silent failures.
