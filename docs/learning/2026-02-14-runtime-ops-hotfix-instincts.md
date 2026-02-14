# Continuous Learning - Runtime Ops Hotfixes (2026-02-14)

## Session Context

- Resolved startup/runtime blockers for notification worker and API local commands before proceeding with deeper Phase 9 validation tasks.

## Learned Instincts

1. `.env` loading must be explicit in CLI-driven runtime modules.
   - Relying on shell export state causes reproducible “I set it in `.env` but app cannot see it” failures.

2. Queue consumers should degrade gracefully when topology is absent.
   - Auto-declare-once behavior prevents crash loops and supports incremental infrastructure bring-up.

3. Package `__init__` should avoid eager import of runnable modules.
   - Lazy exports remove `python -m` runpy warnings and reduce side-effect risk.

4. Migration commands need a network-aware fallback path.
   - Host connectivity assumptions break after internal-network hardening; Docker-network fallback is safer.

## Follow-Up Candidates

- Add optional topology bootstrap for exchange/binding declaration (not queue-only).
- Add dedicated migration helper script with clearer credential-drift diagnostics and reset guidance.
