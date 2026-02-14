# AGENT.md

## Responsibility

Holds architecture, requirements, plans, runbooks, and learning artifacts.

## Architectural Boundaries

- Docs describe system behavior and decisions.
- Docs must not become the only place where executable contracts live.

## Coding Conventions

- Keep sections concise, versioned, and decision-oriented.
- Use exact file paths and explicit dates in change logs.

## Dependency Rules

- Documentation updates should accompany behavior/config changes.

## Extension Rules

- Add new ADRs/plans when decisions alter architecture, interfaces, or rollout risk.

## Integration Contracts

- PRD/ARD/implementation plan are source-of-truth planning artifacts.

## Testing Expectations

- Add doc tests when critical claims require automated guardrails.

## Operational Notes

- Keep readiness statements aligned with actual runnable state.
