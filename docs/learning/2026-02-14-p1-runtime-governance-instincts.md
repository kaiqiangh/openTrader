# Continuous Learning v2 Notes - P1 Runtime Verification and Governance Batch

Source session: `2026-02-14` (`P1-001`, `P0-003`, `P1-006`)

## Atomic Instincts

```yaml
---
id: capture-runtime-verification-as-a-dated-artifact
trigger: "when infrastructure checks are blocked or partially successful"
confidence: 0.84
domain: "operations"
source: "session-observation"
---
action: "Persist runtime verification attempts in a dated document so blockers and evidence are queryable in later phases."
evidence:
  - "`docs/runtime/runtime-verification-2026-02-14.md` records Compose verification outcomes and follow-up context."
```

```yaml
---
id: pin-go-toolchain-for-local-hermetic-tests
trigger: "when Go validation differs across environments"
confidence: 0.83
domain: "tooling"
source: "session-observation"
---
action: "Align `go.mod` with locally available toolchain and run tests with explicit local caches to avoid network-dependent failures."
evidence:
  - "`services/real_execution_go/go.mod` was stabilized at a local-compatible version and validated by unblock tests."
```

```yaml
---
id: add-llm-governance-schema-before-gateway-expansion
trigger: "when introducing model usage features with quotas and audit needs"
confidence: 0.87
domain: "governance"
source: "session-observation"
---
action: "Create governance tables for call logs, usage aggregates, and quota limits before adding advanced LLM runtime behaviors."
evidence:
  - "`migrations/versions/20260214_0004_llm_governance_schema.py` introduced `llm_calls`, usage rollups, and quota limit contracts."
```
