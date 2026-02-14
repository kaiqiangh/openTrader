# Phase 7 Notification Delivery Hardening Design (P7-013 to P7-015)

## Scope

Deliver the next notification tasks:

- `P7-013`: Telegram gateway with sender implementation, safe message templates, and retryability-aware failures.
- `P7-014`: Preference management APIs with per-user/per-strategy/per-event/severity/gateway CRUD.
- `P7-015`: Harden dedupe/rate-limit and retry policy with bounded backoff and explicit DLQ movement.

## Baseline

- Notification runtime already exists (`event_intake`, `policy_router`, `gateway_dispatch`, `service`).
- Source pipeline publishers already emit `notify.events.raw` envelopes.
- API control-plane exists with JWT RBAC and `ops` router patterns.
- Current routing logic supports basic dedupe/rate-limit and a generic in-memory gateway, but no concrete Telegram delivery or preference CRUD.

## Approaches Considered

### Approach A: Keep preferences only inside notification runtime config

- Pros: fewer API changes.
- Cons: does not satisfy `P7-014` control-plane requirement; no operator-managed preferences.

### Approach B (recommended): Add API preference store and map to notification router model

- Pros: explicit CRUD contracts, RBAC validation, and direct compatibility with `NotificationPreference`.
- Cons: introduces extra state models and endpoint surface.

### Approach C: Build persistence-backed preference APIs now (Postgres)

- Pros: production-ready durability.
- Cons: high scope increase for this batch; migration and repository work belongs to later deployment-hardening tasks.

Recommendation: **Approach B** now, with in-memory control-plane store and stable contracts that can be swapped to persistence later.

## Design

### 1) Telegram gateway and template layer (`P7-013`)

- Add `services/notification_service/telegram_gateway.py`:
  - `TelegramGatewayConfig` for token/default-chat-id/timeout/parse-mode.
  - `TelegramGateway` implementing `NotificationGateway`.
  - `TelegramGatewayError` with `retryable` flag and error codes.
  - Safe formatting helper for MarkdownV2 escaping and deterministic message template.
- HTTP behavior:
  - Retryable: network timeout, 429, 5xx.
  - Terminal: auth/config errors, malformed requests, invalid chat.

### 2) Preference management APIs (`P7-014`)

- Extend API state with notification preference records and CRUD helpers.
- Add models for request/response contracts with strict validation:
  - `user_id`, `min_severity`, `gateways`, optional `strategy_ids`, optional `event_types`.
- Add `ops` endpoints:
  - `GET /ops/notifications/preferences`
  - `PUT /ops/notifications/preferences/{user_id}` (idempotent upsert)
  - `DELETE /ops/notifications/preferences/{user_id}`
- RBAC:
  - `GET`: viewer+
  - `PUT`/`DELETE`: admin

### 3) Spam control + retry policy hardening (`P7-015`)

- Harden `NotificationPolicyRouter`:
  - deterministic dedupe and rate-limit suppression decisions.
  - suppression stats surface for debugging/tests.
- Harden `GatewayDispatcher`:
  - bounded exponential backoff (`base_delay * factor^(attempt-1)` with max cap).
  - retry only for retryable errors; terminal failures move directly to DLQ.
  - keep explicit attempt count and failure details.

## Test Strategy

- Add/extend unit tests for:
  - Telegram template escaping and retryability mapping.
  - Preference API CRUD, validation, and RBAC behavior.
  - Dispatcher backoff/retry behavior and DLQ outcomes.
  - Policy router dedupe/rate-limit suppression counters.
- Run full regression (`pytest`, `ruff`, Go tests).

## Risks

- Telegram API behavior differences across parse modes.
  - Mitigation: isolate parser/escape logic and use deterministic unit tests.
- Preference model drift between API and notification runtime.
  - Mitigation: single adapter conversion in API state and test coverage.
