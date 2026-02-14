# Continuous Learning v2 Notes - P3 Metrics and Tracing Batch

Source session: `2026-02-14` (`P3-012`)

## Atomic Instincts

```yaml
---
id: wrap-agent-stages-with-latency-and-failure-metrics
trigger: "when orchestrator executes planner/risk/execution/guardrail stages"
confidence: 0.89
domain: "observability"
source: "session-observation"
---
action: "Measure each stage with monotonic timing and record both success and failure outcomes so failure rates and p95-like rollups can be computed later."
evidence:
  - "AgentOrchestrator now records stage metrics for market context, planner, risk, execution decision, guardrail, and memory stages."
```

```yaml
---
id: keep-llm-token-metrics-on-call-path
trigger: "when LLM gateway returns success/failure/quota-block outcomes"
confidence: 0.86
domain: "llm-governance"
source: "session-observation"
---
action: "Emit token/cost/latency usage metrics directly from gateway call outcomes to avoid drift between persisted audit records and runtime telemetry."
evidence:
  - "LLMGateway now invokes metrics sink recording prompt/completion/total tokens and status per request scope."
```

```yaml
---
id: expose-one-stable-metrics-snapshot-contract
trigger: "when dashboards or replay tooling need runtime observability payloads"
confidence: 0.84
domain: "api-contracts"
source: "session-observation"
---
action: "Provide one deterministic snapshot shape for stage metrics, LLM usage aggregates, and recent spans so downstream readers do not parse internal state."
evidence:
  - "AgentRuntimeMetrics.snapshot() now returns stable sections: agent_stages, llm_usage, recent_spans."
```
