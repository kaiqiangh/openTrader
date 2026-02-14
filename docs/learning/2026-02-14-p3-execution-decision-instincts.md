# Continuous Learning v2 Notes - P3 Execution Decision Batch

Source session: `2026-02-14` (`P3-004`)

## Atomic Instincts

```yaml
---
id: normalize-final-actions-through-explicit-agent
trigger: "when converting planner+risk outputs into executable intents"
confidence: 0.85
domain: "agentic-runtime"
source: "session-observation"
---
action: "Use a dedicated execution decision agent to normalize action enums and quantity signs before publishing execution intents."
evidence:
  - "ExecutionDecisionAgent constrains outputs to BUY/SELL/HOLD/CLOSE and normalizes quantity semantics."
```

```yaml
---
id: publish-only-executable-approved-intents
trigger: "when final action could be hold or non-executable"
confidence: 0.84
domain: "backend-patterns"
source: "session-observation"
---
action: "Publish execution intents only when risk is approved and the action/quantity pair is executable; always emit lifecycle trace events regardless."
evidence:
  - "AgentOrchestrator emits action_proposed lifecycle events and gates intent publishing on schema-valid BUY/SELL/CLOSE with non-zero quantity."
```

```yaml
---
id: track-action-proposal-stage-in-lifecycle
trigger: "when expanding decision pipeline stages"
confidence: 0.82
domain: "observability"
source: "session-observation"
---
action: "Insert an explicit action_proposed lifecycle event between risk evaluation and intent publishing to preserve deterministic replay checkpoints."
evidence:
  - "Lifecycle now includes agent.decision.action_proposed before agent.decision.intent_published."
```
