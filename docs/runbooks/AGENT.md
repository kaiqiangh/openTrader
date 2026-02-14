# AGENT.md

## Responsibility

Defines operator incident-response runbooks for production and pre-production failure scenarios.

## Architectural Boundaries

- Documentation-only module.
- No implementation logic or generated telemetry data stored here.

## Coding Conventions

- Keep procedures actionable and time-ordered.
- Use deterministic command examples and explicit expected outcomes.
- Include rollback and validation checkpoints for each incident class.

## Dependency Rules

- Runbooks may reference service/docs/config paths.
- Runbooks must not assume unstated infrastructure beyond repository-defined stack.

## Extension Rules

- New incident classes require: detection signals, immediate actions, escalation, recovery validation, and post-incident actions.

## Integration Contracts

- Alert names in runbooks should match `config/observability/alerts.yml`.
- Commands should align with current `docker-compose.yml` service names and profiles.

## Testing Expectations

- Tests validate runbook file presence and required section coverage.

## Operational Notes

- Treat runbooks as living documents and revise after every meaningful incident retro.
