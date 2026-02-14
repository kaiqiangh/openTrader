# Phase 7 Notification Test Suite Expansion Design (P7-017)

## Scope

Implement `P7-017` by expanding notification validation with:

- fault-injection coverage for retry/terminal failure paths
- publish-to-deliver integration coverage from source bridge output into notification runtime
- documentation and plan updates reflecting the expanded validation baseline

## Current Baseline

- Unit tests already cover intake classification, basic policy dedupe/rate-limit, dispatcher retries, Telegram status mapping, and observability snapshots.
- Missing focused scenarios:
  - explicit terminal exception behavior (`retryable=False`) and no extra retry delay
  - retry exhaustion path with deterministic backoff and DLQ movement
  - end-to-end bridge envelope publish followed by service delivery in one flow

## Design Decisions

### 1) Fault-injection tests in dedicated suite

- Add targeted tests for `GatewayDispatcher` behavior under:
  - terminal exceptions
  - retryable failures that exhaust max attempts
  - unregistered gateway DLQ behavior
- Reuse deterministic sleep hook to verify bounded backoff sequence.

### 2) Publish->deliver integration test

- Use `NotificationEventBridge` with capture publisher.
- Feed captured `notify.events.raw` envelope into `NotificationService`.
- Assert delivery result, message metadata, and observability counters.

### 3) Documentation and plan consistency gates

- Update test/docs guard to mark `P7-017` done in implementation plan.
- Keep README and AGENT docs aligned with expanded validation expectations.

## Validation Plan

- Run targeted suite first for new tests.
- Run full regressions (`pytest`, `ruff`, Go tests).
