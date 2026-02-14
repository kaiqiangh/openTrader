# Continuous Learning v2 Notes - Notification Docs and Gap Review Batch

Source session: `2026-02-14` (`notification architecture updates`, `phase 0-3 gap review`, `AGENT.md rollout`)

## Atomic Instincts

```yaml
---
id: evolve-prd-ard-and-implementation-plan-together
trigger: "when introducing cross-cutting platform capabilities"
confidence: 0.83
domain: "docs-governance"
source: "session-observation"
---
action: "Update product requirements, architecture design, and implementation sequencing in one pass so delivery plans stay coherent."
evidence:
  - "Notification architecture updates were synchronized across `docs/PRD_Consolidated.md`, `docs/ARD_Consolidated.md`, and `docs/IMPLEMENTATION_PLAN.md`."
```

```yaml
---
id: publish-severity-ranked-gap-reports-before-next-phase
trigger: "when plan status claims may hide integration gaps"
confidence: 0.87
domain: "risk-management"
source: "session-observation"
---
action: "Produce an explicit severity-ranked gap report with remediation steps before green-lighting the next major phase."
evidence:
  - "`docs/reviews/2026-02-14-phase0-3-gap-analysis.md` captures critical/important findings and a remediation plan."
```

```yaml
---
id: codify-directory-boundaries-with-agent-guides
trigger: "when repository scope and service boundaries expand quickly"
confidence: 0.8
domain: "workflow"
source: "session-observation"
---
action: "Add scoped `AGENT.md` files at root and major directories to keep conventions and boundaries discoverable."
evidence:
  - "Root and nested guides (for example `AGENT.md`, `services/AGENT.md`, and `docs/AGENT.md`) were rolled out together."
```
