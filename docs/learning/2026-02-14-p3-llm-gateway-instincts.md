# Continuous Learning v2 Notes - P3 LLM Gateway Batch

Source session: `2026-02-14` (`P3-006`)

## Atomic Instincts

```yaml
---
id: centralize-llm-routing-through-gateway
trigger: "when multiple agents need model access"
confidence: 0.85
domain: "backend-patterns"
source: "session-observation"
---
action: "Route all model calls through one gateway contract with explicit provider ordering and fallback semantics."
evidence:
  - "LLMGateway resolves provider order and performs fallback across configured aliases."
```

```yaml
---
id: enforce-timeout-before-retry
trigger: "when provider calls can stall"
confidence: 0.84
domain: "reliability"
source: "session-observation"
---
action: "Apply per-provider timeout guard before retry/fallback loops to keep decision latency bounded."
evidence:
  - "Gateway wraps provider client calls with asyncio.wait_for using ProviderSettings.timeout_ms."
```

```yaml
---
id: normalize-response-shape-at-boundary
trigger: "when provider payloads differ"
confidence: 0.82
domain: "api-design"
source: "session-observation"
---
action: "Normalize content and usage at gateway boundary so downstream persistence and quota checks can stay provider-agnostic."
evidence:
  - "Gateway extracts content/usage into LLMResponse regardless of raw payload variation."
```
