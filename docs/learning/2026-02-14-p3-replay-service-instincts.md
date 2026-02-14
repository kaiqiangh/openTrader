# Continuous Learning v2 Notes - P3 Replay Service Batch

Source session: `2026-02-14` (`P3-011`)

## Atomic Instincts

```yaml
---
id: sort-trace-artifacts-before-replay
trigger: "when reconstructing decision history from persisted traces"
confidence: 0.88
domain: "replay"
source: "session-observation"
---
action: "Sort agent runs, agent messages, and LLM calls with stable keys before building replay outputs so reconstruction is deterministic."
evidence:
  - "DecisionReplayService orders runs/messages/llm calls before graph assembly and digest generation."
```

```yaml
---
id: include-memory-summary-in-replay-graph
trigger: "when long-term decision memory is available for a replay request"
confidence: 0.84
domain: "agentic-runtime"
source: "session-observation"
---
action: "Merge long-term memory summary and lifecycle into replay output so replay consumers can inspect final state and stage transitions from one artifact."
evidence:
  - "Replay output includes summary/lifecycle and a memory_summary graph node linked to the decision node."
```

```yaml
---
id: hash-normalized-replay-payload
trigger: "when replay reproducibility must be verified"
confidence: 0.86
domain: "observability"
source: "session-observation"
---
action: "Compute a deterministic digest over normalized replay payloads to verify repeated replay requests produce equivalent results."
evidence:
  - "DecisionReplayResult exposes deterministic_digest generated from stable JSON serialization."
```
