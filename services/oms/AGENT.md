# AGENT.md

## Responsibility

Manages order lifecycle state, fill reconciliation, and order event publication.

## Architectural Boundaries

- Owns lifecycle transitions and consistency checks.
- Owns queue+exchange fill reconciliation and canonical order-fill convergence.
- Owns position netting and portfolio snapshot calculation from reconciled fills.
- Must not bypass risk policy decisions.

## Coding Conventions

- State transitions should be explicit and validated.
- Idempotency must be enforced for repeated exchange/order events.
- Keep lifecycle changes centralized in `state_machine.py` transition matrix updates.

## Dependency Rules

- Depends on execution events, persistence adapters, and risk controls.

## Extension Rules

- Any new order state requires transition matrix and migration/test updates.

## Integration Contracts

- Publishes order updates for API, risk, replay, and notifications.
- `fill_reconciliation.py` merges queue lifecycle events with exchange fallback snapshots.
- `position_engine.py` applies normalized fill events into mode-tagged position state.
- `portfolio_snapshot.py` derives NAV and PnL snapshots from balances + marked positions.

## Testing Expectations

- Transition matrix tests and reconciliation edge-case tests are required.

## Operational Notes

- Ensure eventual consistency handling for delayed exchange updates.
