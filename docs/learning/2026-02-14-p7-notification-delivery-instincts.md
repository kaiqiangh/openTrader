# Continuous Learning - P7 Notification Delivery Hardening (2026-02-14)

## Session Context

- Implemented `P7-013`, `P7-014`, and `P7-015` on top of existing Phase 7 notification baseline.
- Scope included Telegram delivery, preference management APIs, and anti-spam/retry reliability hardening.

## Learned Instincts

1. Test-first across mixed API/runtime batches prevents hidden contract drift.
   - Writing docs/plan assertions (`tests/test_p7_api_docs.py`) plus runtime tests catches coordination failures early.

2. Retry semantics should be encoded in delivery status, not only exceptions.
   - Returning explicit statuses (`DELIVERED`, `RETRYABLE_ERROR`, `FAILED_TERMINAL`) made dispatcher policy deterministic and easier to unit test.

3. Bounded backoff with injectable sleep hooks is the safest default for infra-facing modules.
   - Production code uses async sleep; tests inject a collector to assert exact delay progression without adding runtime cost.

4. Notification preference APIs benefit from idempotent upsert shape keyed by `user_id`.
   - `PUT /ops/notifications/preferences/{user_id}` reduced control-plane complexity while preserving audit fields.

5. MarkdownV2 escape coverage is critical for Telegram.
   - Template tests should include reserved characters from titles and free-text bodies to prevent silent delivery failures.

## Follow-Up Candidates

- Promote in-memory notification preferences and DLQ records to persistence-backed repositories in `P7-018`.
- Add delivery metrics and traces in `P7-016` to monitor retry depth, terminal failures, and suppression counters.
