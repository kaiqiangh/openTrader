# AGENT.md

## Responsibility

Provides notification runtime core for event intake, policy routing, gateway dispatch, concrete Telegram delivery, and notification telemetry.

## Architectural Boundaries

- Notification module consumes normalized source events and produces delivery attempts/outcomes.
- Do not place strategy, risk, or OMS domain rules here; this module maps and routes events only.

## Coding Conventions

- Keep provider-specific logic behind gateway interfaces.
- Use typed severity and explicit routing decisions.
- Preserve idempotency metadata through every stage.
- Keep template rendering deterministic and escape Telegram MarkdownV2 reserved characters.

## Dependency Rules

- May depend on shared envelope contracts and service-level source event publishers.
- Must not depend on API router internals.

## Extension Rules

- New gateway support must implement the gateway protocol and not alter policy-router semantics.
- New event-classification rules must be covered by intake tests.
- Retry/backoff behavior must remain bounded and deterministic in tests.

## Integration Contracts

- Input: canonical envelopes from source pipelines.
- Output: delivery results and DLQ records with traceable metadata.
- Publisher bridge emits `notify.*` source events for downstream notification processing.
- Telegram gateway reads `TELEGRAM_BOT_TOKEN` and `TELEGRAM_DEFAULT_CHAT_ID` config when enabled.
- Observability collector emits in-memory metrics/log/trace snapshots for control-plane dashboards.

## Testing Expectations

- Unit tests required for severity mapping, preference filters, dedupe/rate-limit, dispatch retries, DLQ paths, and observability snapshots.
- Cover retryable vs terminal gateway failures and template escaping paths.

## Operational Notes

- Keep limits/backoff configurable and deterministic for replay/test environments.
