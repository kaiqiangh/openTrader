# Continuous Learning v2 Notes - P3 LLM Persistence Batch

Source session: `2026-02-14` (`P3-007`)

## Atomic Instincts

```yaml
---
id: persist-llm-call-records-on-success-and-failure
trigger: "when gateway calls can partially fail across providers"
confidence: 0.86
domain: "observability"
source: "session-observation"
---
action: "Persist one immutable call record for both successful responses and terminal failures so replay/audit never depends on transient logs."
evidence:
  - "LLMGateway writes LLMCallRecord with response_payload.status set to succeeded or failed."
```

```yaml
---
id: estimate-cost-at-gateway-boundary
trigger: "when downstream quota/usage controls need deterministic cost inputs"
confidence: 0.83
domain: "governance"
source: "session-observation"
---
action: "Compute estimated cost directly from normalized usage tokens and provider rates before persistence."
evidence:
  - "Gateway uses prompt/completion per-1k token rates in ProviderSettings to derive estimated_cost."
```

```yaml
---
id: keep-prompt-response-payloads-raw
trigger: "when replay and forensic debugging require full context"
confidence: 0.84
domain: "agentic-runtime"
source: "session-observation"
---
action: "Store full prompt and response payloads as immutable record fields and avoid lossy transformations in persistence boundary."
evidence:
  - "LLMCallRecord includes full prompt_payload and response_payload maps."
```
