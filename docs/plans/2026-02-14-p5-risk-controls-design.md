# Phase 5 Risk Controls Design (P5-005 to P5-007)

## Context

Phase 5 currently has OMS lifecycle (`P5-001`), fill reconciliation (`P5-002`), position engine (`P5-003`), and portfolio snapshots (`P5-004`) in place. The missing slice is risk-authoritative enforcement after these accounting primitives: core risk limits, drawdown/daily loss guards, and emergency stop controls.

## Approach Options

### Option A (Recommended): Composable rule engine + account guards + control gate

- Build a dedicated `services/oms/risk_rules.py` module with typed inputs and per-rule evaluation results.
- Build `services/oms/risk_guards.py` for account-level drawdown/daily-loss policy checks using portfolio snapshots.
- Build `services/oms/risk_controls.py` for circuit breaker and kill-switch state, including event publication contracts.
- Keep orchestration minimal and deterministic: `RiskPolicyEngine` composes all checks and returns one decision artifact.

Trade-offs:
- Pros: clear separation of rule families, easy extension for future policies/telemetry, deterministic tests.
- Cons: introduces three modules and additional contracts up front.

### Option B: Single monolithic risk module

- Put all rules and controls into one `risk.py` file.

Trade-offs:
- Pros: fastest to type initially.
- Cons: harder to evolve, poor boundary clarity for future P5-008/P5-009 observability/regression packs.

### Option C: Reuse agent guardrail layer for OMS risk

- Route OMS checks through `services/agent_orchestrator/guardrail_validation.py` with minor extension.

Trade-offs:
- Pros: less net-new code.
- Cons: conflates pre-trade strategy decision validation with post-OMS/account risk policies; weak separation of concerns.

## Selected Design

Option A.

### Module boundaries

- `risk_rules.py`: position notional, leverage, per-symbol exposure.
- `risk_guards.py`: max drawdown and daily loss.
- `risk_controls.py`: circuit breaker + kill switch + emergency event log.
- `risk_policy.py`: composition layer that evaluates in order and returns a unified decision.

### Data flow

1. Incoming order intent proposes side/quantity/price.
2. `RiskPolicyEngine` calculates projected exposure using position snapshot.
3. Core rules (`P5-005`) evaluate and can deny immediately.
4. Account guards (`P5-006`) evaluate current portfolio stress.
5. Emergency controls (`P5-007`) check if kill switch is enabled or circuit breaker is open.
6. Result returns `allowed`, `blocked_by`, severity, and rule outcomes for observability/replay.

### Error handling

- Contract validation errors raise explicit `ValueError` derivatives.
- Rule failures are not exceptions; they are policy outcomes.
- Control-plane operations (trip/reset/enable/disable) are idempotent.

### Testing

- Unit tests per module (`risk_rules`, `risk_guards`, `risk_controls`, `risk_policy`).
- Docs test updated to verify README + implementation plan mention new P5 modules/status.

## Success criteria

- `P5-005`, `P5-006`, `P5-007` task rows move to `DONE` with passing tests.
- Risk policy output is deterministic and replay-friendly.
- Emergency controls emit structured events for future notifications/API surfaces.
