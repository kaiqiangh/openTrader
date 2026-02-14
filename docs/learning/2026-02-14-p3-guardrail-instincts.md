# Continuous Learning v2 Notes - P3 Guardrail Validation Batch

Source session: `2026-02-14` (`P3-009`)

## Atomic Instincts

```yaml
---
id: validate-before-publish-intent
trigger: "when execution decisions are generated but not yet dispatched"
confidence: 0.86
domain: "risk-controls"
source: "session-observation"
---
action: "Run a dedicated guardrail validator after action proposal and before intent publishing; block dispatch when any hard guardrail fails."
evidence:
  - "AgentOrchestrator now emits guardrail_passed/guardrail_rejected and gates intent publish on guardrail.allowed."
```

```yaml
---
id: encode-guardrail-failures-as-structured-violations
trigger: "when guardrail checks reject a decision"
confidence: 0.84
domain: "observability"
source: "session-observation"
---
action: "Return machine-readable violation codes and detail payloads so replay and operations tooling can reason about rejection causes deterministically."
evidence:
  - "GuardrailValidationResult exposes blocked_by and GuardrailViolation entries with codes and details."
```

```yaml
---
id: separate-risk-rejection-from-guardrail-rejection
trigger: "when multiple gating layers exist in decision pipeline"
confidence: 0.82
domain: "agentic-runtime"
source: "session-observation"
---
action: "Keep status semantics explicit by differentiating RISK_REJECTED from GUARDRAIL_REJECTED states in orchestration results."
evidence:
  - "Orchestrator assigns GUARDRAIL_REJECTED when risk passes but guardrail validation fails."
```
