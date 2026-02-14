# Continuous Learning v2 Notes - P3 LLM Quota Enforcement Batch

Source session: `2026-02-14` (`P3-008`)

## Atomic Instincts

```yaml
---
id: enforce-hard-quotas-before-provider-dispatch
trigger: "when llm usage has strict daily/monthly limits"
confidence: 0.86
domain: "governance"
source: "session-observation"
---
action: "Run hard-limit quota checks before any provider call to prevent over-budget model usage at source."
evidence:
  - "LLMGateway blocks requests with LLMQuotaExceededError before provider dispatch when projected usage breaches limits."
```

```yaml
---
id: update-quota-usage-from-real-outcome
trigger: "when quota usage should reflect actual model spend"
confidence: 0.83
domain: "billing-observability"
source: "session-observation"
---
action: "Increment quota usage only from successful call outcomes using normalized total_tokens and estimated_cost values."
evidence:
  - "Gateway calls quota_store.increment_usage after successful provider response normalization."
```

```yaml
---
id: persist-quota-blocked-records
trigger: "when quota guard blocks requests"
confidence: 0.82
domain: "auditability"
source: "session-observation"
---
action: "Persist a quota_blocked record with reason and projections so operators can audit denied requests without relying on runtime logs."
evidence:
  - "Gateway emits response_payload.status=quota_blocked via LLMCallRecord when hard-limit checks fail."
```
