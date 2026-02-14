# Continuous Learning v2 Notes - P3 Agent Runtime Batch

Source session: `2026-02-14` (`P3-001`, `P3-002`, `P3-003`)

## Atomic Instincts

```yaml
---
id: orchestrate-with-explicit-lifecycle-envelopes
trigger: "when building multi-agent decision runtimes"
confidence: 0.84
domain: "backend-patterns"
source: "session-observation"
---
action: "Emit envelope-validated lifecycle events for each decision stage so trace replay does not depend on implicit logs."
evidence:
  - "AgentOrchestrator publishes received/planned/risk/intended lifecycle events to strategy.decision.lifecycle."
```

```yaml
---
id: planner-should-stay-deterministic-before-llm
trigger: "when introducing planner baseline before llm gateway"
confidence: 0.82
domain: "agentic-runtime"
source: "session-observation"
---
action: "Start with deterministic market microstructure rules and stable metrics to lock contracts before model-backed planners are introduced."
evidence:
  - "PlannerAgent computes orderbook imbalance thresholds into BUY/SELL/HOLD outputs."
```

```yaml
---
id: risk-output-must-explain-blockers
trigger: "when implementing pre-trade risk gates"
confidence: 0.87
domain: "risk-controls"
source: "session-observation"
---
action: "Return structured risk signals plus blocked_by identifiers so orchestrator routing and operator debugging remain deterministic."
evidence:
  - "RiskAgent exposes signal-level pass/fail with blocked_by list and risk_score."
```
