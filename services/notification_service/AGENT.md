# AGENT.md

## Responsibility

Provides notification runtime core for event intake, policy routing, and gateway dispatch.

## Architectural Boundaries

- Notification module consumes normalized source events and produces delivery attempts/outcomes.
- Do not place strategy, risk, or OMS domain rules here; this module maps and routes events only.

## Coding Conventions

- Keep provider-specific logic behind gateway interfaces.
- Use typed severity and explicit routing decisions.
- Preserve idempotency metadata through every stage.

## Dependency Rules

- May depend on shared envelope contracts and service-level source event publishers.
- Must not depend on API router internals.

## Extension Rules

- New gateway support must implement the gateway protocol and not alter policy-router semantics.
- New event-classification rules must be covered by intake tests.

## Integration Contracts

- Input: canonical envelopes from source pipelines.
- Output: delivery results and DLQ records with traceable metadata.
- Publisher bridge emits `notify.*` source events for downstream notification processing.

## Testing Expectations

- Unit tests required for severity mapping, preference filters, dedupe/rate-limit, dispatch retries, and DLQ paths.

## Operational Notes

- Keep limits configurable and deterministic for replay/test environments.
