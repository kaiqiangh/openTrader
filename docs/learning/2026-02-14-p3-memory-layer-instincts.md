# Continuous Learning v2 Notes - P3 Memory Layer Batch

Source session: `2026-02-14` (`P3-010`)

## Atomic Instincts

```yaml
---
id: hydrate-short-term-before-falling-back-long-term
trigger: "when decision-cycle context is needed at orchestrator entry"
confidence: 0.84
domain: "agentic-runtime"
source: "session-observation"
---
action: "Read per-decision short-term memory first and only use long-term fallback when short-term slots are absent."
evidence:
  - "AgentMemoryLayer reads Redis-like slots first, then loads Postgres summary fallback for missing warm state."
```

```yaml
---
id: persist-stage-outputs-by-slot
trigger: "when agent stages produce context/plan/risk/decision/guardrail outputs"
confidence: 0.86
domain: "memory-governance"
source: "session-observation"
---
action: "Write each stage output to deterministic decision slots so replay/debug tooling can inspect intermediate state without log parsing."
evidence:
  - "Orchestrator now writes context, plan, risk, execution_decision, guardrail, and status slots per decision cycle."
```

```yaml
---
id: cache-long-term-summary-back-into-short-term
trigger: "when final decision summary is persisted"
confidence: 0.81
domain: "performance"
source: "session-observation"
---
action: "After durable persistence, mirror summary to short-term memory for low-latency follow-up reads in the same operational window."
evidence:
  - "AgentMemoryLayer persists DecisionMemoryRecord and writes the summary slot with the same decision TTL."
```
