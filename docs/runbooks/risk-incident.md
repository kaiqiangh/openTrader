# Risk Incident Runbook

## Scope

Incident response workflow for drawdown/daily-loss breaches, circuit-breaker trips, or unexpected kill-switch activations.

## Detection Signals

- Alert fired: `RiskDrawdownBreach`
- Risk status endpoint reports active blockers (`drawdown_exceeded`, `daily_loss_exceeded`, `kill_switch_enabled`)
- Notification stream emits critical risk events
- OMS rejection volume increases for risk-policy-denied actions

## Immediate Actions

1. Freeze new risk-increasing actions:
   - enable kill switch if not already enabled.
2. Confirm incident type:
   - drawdown breach
   - daily loss breach
   - manual/emergency control trip
3. Validate portfolio/position state:
   - inspect latest portfolio snapshot and open positions.
4. Communicate protective state to operators and stakeholders.

## Escalation

1. Notify risk owner and on-call operations lead immediately.
2. Escalate to incident commander if losses continue after kill-switch enforcement.

## Recovery Validation

1. Verify no new non-compliant orders are accepted while controls are active.
2. Confirm risk metrics return below configured thresholds or risk owner signs off override.
3. Re-enable trading controls in staged sequence:
   - reset circuit breaker
   - disable kill switch
   - re-enable strategies incrementally

## Post-Incident Actions

1. Record breach trigger conditions and operator actions timeline.
2. Review and tune risk limits, guardrail thresholds, and strategy sizing.
3. Backfill tests and dashboards for any blind spots discovered.
