# AGENT.md

## Responsibility

Manages order lifecycle state, fill reconciliation, positions/portfolio accounting, and OMS-side
risk-authoritative enforcement controls.

## Architectural Boundaries

- Owns lifecycle transitions and consistency checks.
- Owns queue+exchange fill reconciliation and canonical order-fill convergence.
- Owns position netting and portfolio snapshot calculation from reconciled fills.
- Owns core risk checks, drawdown/daily-loss guards, and emergency kill-switch/circuit-breaker state.
- Must not bypass risk policy decisions.

## Coding Conventions

- State transitions should be explicit and validated.
- Idempotency must be enforced for repeated exchange/order events.
- Keep lifecycle changes centralized in `state_machine.py` transition matrix updates.
- Risk decisions must be deterministic and replay-friendly (`blocked_by` codes are required).

## Dependency Rules

- Depends on execution events and persistence adapters.
- Exposes control/evaluation outputs for API, notifications, and replay consumers.

## Extension Rules

- Any new order state requires transition matrix and migration/test updates.
- Any new risk rule/guard must include unit tests and stable rule-code naming.

## Integration Contracts

- Publishes order updates for API, risk, replay, and notifications.
- `fill_reconciliation.py` merges queue lifecycle events with exchange fallback snapshots.
- `position_engine.py` applies normalized fill events into mode-tagged position state.
- `portfolio_snapshot.py` derives NAV and PnL snapshots from balances + marked positions.
- `risk_rules.py` evaluates projected position/notional/leverage limits.
- `risk_guards.py` evaluates account drawdown and daily-loss guardrails.
- `risk_controls.py` controls kill-switch and circuit-breaker state with control events.
- `risk_policy.py` composes rule, guard, and control outputs into one allow/deny decision.
- `risk_observability.py` records risk decision/control telemetry and severity-classified events.

## Testing Expectations

- Transition matrix tests and reconciliation edge-case tests are required.
- Risk observability counters/events and regression scenarios are required for policy changes.

## Operational Notes

- Ensure eventual consistency handling for delayed exchange updates.
