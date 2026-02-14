# AGENT.md

## Responsibility

Builds symbol/global news summaries and relevance metadata for agent context.

## Architectural Boundaries

- Summarization and relevance scoring only.
- Owns strategy-context bridge contracts for publishing/injecting summary context.
- Owns resilience fallback policy for stale/missing news summaries.
- Must not publish execution intents.
- Must not own source fetch or connector retry logic.

## Coding Conventions

- Keep summarization windows, freshness rules, and confidence metadata explicit.
- Fallback summary output must be deterministic (`news_unavailable`) when no scoped inputs exist.

## Dependency Rules

- Depends on normalized news inputs and LLM gateway (if model-based summarization is used).

## Extension Rules

- New summarization models require quality and latency validation.

## Integration Contracts

- Publishes summary artifacts for market context enrichment.
- `summarizer_service.py` produces `news_summaries`-compatible artifacts (`summary_id`, `symbol_scope`, `window_start`, `window_end`, `summary_text`, `token_count`, `generated_at`).
- `context_injection_bridge.py` publishes envelope-validated summary context events and injects `news` payload fields for market context agent input.
- `resilience.py` evaluates staleness/unavailability fallback and publishes `news.alerts` envelopes in degraded mode.

## Testing Expectations

- Validate freshness, relevance, and fallback behavior under missing data.
- Validate context bridge envelope publishing and resilience alert emission behavior.

## Operational Notes

- Summarizer failures should emit degraded-mode signals, not halt orchestration.
