# Continuous Learning v2 Notes - P0 Bootstrap Batch

Source session: `2026-02-14` (`P0-001`, `P0-002`, `P0-003`, `P0-004`, `P0-005`, `P0-006`, `P0-007`)

## Atomic Instincts

```yaml
---
id: lock-repo-skeleton-with-presence-tests
trigger: "when bootstrapping a multi-service monorepo"
confidence: 0.82
domain: "workflow"
source: "session-observation"
---
action: "Write directory/file presence tests first so service-layout drift is caught before implementation phases begin."
evidence:
  - "tests/test_repo_layout.py enforces required service directories before feature work."
```

```yaml
---
id: treat-env-contract-as-code
trigger: "when establishing shared runtime configuration"
confidence: 0.86
domain: "configuration"
source: "session-observation"
---
action: "Define required environment keys in both `.env.example` and a validator script to keep local and CI runtime assumptions aligned."
evidence:
  - "scripts/validate_env.py checks REQUIRED_KEYS mirrored from `.env.example` baseline contracts."
```

```yaml
---
id: bootstrap-dev-flow-through-make-and-ci
trigger: "when creating initial contributor onboarding paths"
confidence: 0.81
domain: "developer-experience"
source: "session-observation"
---
action: "Ship reproducible local commands and CI checks together so onboarding, lint, and test expectations stay consistent."
evidence:
  - "Makefile targets and `.github/workflows/ci.yml` establish the same baseline test/lint execution flow."
```
