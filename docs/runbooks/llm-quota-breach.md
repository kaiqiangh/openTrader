# LLM Quota Breach Runbook

## Scope

Incident response workflow when model usage breaches configured token/cost limits or repeatedly triggers quota-denied decisions.

## Detection Signals

- Alert fired: `LLMQuotaBreach`
- Governance endpoints show rising breach counters
- Notification events indicate quota-denied decisions
- Strategy decision throughput drops due quota gating

## Immediate Actions

1. Confirm quota scope:
   - Identify strategy/agent pair(s) breaching limits via governance API.
2. Apply containment:
   - disable impacted strategy, or
   - force reduced-frequency mode and conservative routing.
3. Preserve audit artifacts:
   - snapshot recent `llm_calls`, breach records, and decision traces.
4. Validate fallback behavior:
   - ensure non-LLM fallback paths remain deterministic where configured.

## Escalation

1. Notify on-call owner with:
   - breached limit type (daily token/monthly cost)
   - affected strategy IDs
   - estimated cost impact
2. Escalate to product/risk owner before lifting hard limits.

## Recovery Validation

1. Confirm breach counter stabilization after mitigation.
2. Verify strategy decisions no longer fail due quota gating.
3. If limits are adjusted, validate updated limits through governance APIs and a small canary run.

## Post-Incident Actions

1. Document root cause (usage spike, model drift, misconfigured limits).
2. Tune quota thresholds, model routing, or prompt budget controls.
3. Add targeted regression tests for the discovered failure path.
