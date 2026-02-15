# P9-007 to P9-009 Release Readiness Design

## Scope

Complete the final Phase 9 items:

- `P9-007`: data integrity audits for resync/gap detection/kline reconstruction fault behavior.
- `P9-008`: security acceptance validation for encryption, RBAC, network isolation, and secret handling.
- `P9-009`: release checklist + cutover package with rollback and verification gates.

## Candidate Approaches

1. Manual checklist-only completion.
   - Pros: minimal coding.
   - Cons: weak regression confidence and no automated gate.
2. Deterministic automated acceptance suite + evidence docs (recommended).
   - Pros: reproducible, CI-friendly, and aligns with existing Phase 9 gate patterns.
   - Cons: adds more documentation/tests to maintain.
3. Full environment chaos + penetration style exercises.
   - Pros: deeper operational realism.
   - Cons: too heavy for this phase closeout and local CI cadence.

## Selected Design

Choose approach 2 with four deliverables:

1. `P9-007` data integrity audit test suite:
   - audit sequence gap classification and resync request context,
   - verify order book sync raises sequence-gap faults and recovers via snapshot reload,
   - verify kline reconstruction validator catches missing intervals and interval mismatch faults.

2. `P9-008` security acceptance suite:
   - assert RBAC separation on control-plane mutating endpoints,
   - assert encrypted secret storage remains non-plaintext at rest and round-trips correctly,
   - assert compose network exposure boundaries and notification secret-placeholder rejection.

3. `P9-009` release package:
   - release checklist document (preflight, cutover, post-cutover verification, sign-offs),
   - rollback and incident fallback document for first-hour operations.

4. Phase 9 closure docs and plan updates:
   - extend validation docs tests to enforce new artifacts,
   - update README references and `IMPLEMENTATION_PLAN.md` status/ledger/task-board/next-actions.
