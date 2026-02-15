# Continuous Learning - Runtime DB Policy Hardening (2026-02-15)

## Session Context

- Addressed confusion around SQLite usage by adding a shared runtime DB layer and explicit Postgres-first policy.
- Fixed/validated `IMPLEMENTATION_PLAN.md` formatting regressions that impacted doc-contract tests.

## Learned Instincts

1. Production data policy must be enforced in code, not only in documentation.
   - A runtime DB settings loader that rejects SQLite by default prevents accidental local-only persistence from leaking into runtime paths.

2. SQLite still has value as a deterministic test backend when explicitly gated.
   - Keeping `ALLOW_SQLITE_RUNTIME=true` as an opt-in preserves fast tests without weakening production defaults.

3. Progress-plan docs are part of executable contracts in this repo.
   - Table-cell formatting in `IMPLEMENTATION_PLAN.md` (for example `| DONE |`) should be treated as stability-sensitive test surface.

## Follow-Up Candidates

- Wire shared runtime DB settings/engine directly into worker startup paths and service store factories.
- Replace remaining in-memory worker state with persisted Postgres-backed runtime stores to close `P10-003`.
