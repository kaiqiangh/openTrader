# AGENT.md

## Responsibility

Builds symbol/global news summaries and relevance metadata for agent context.

## Architectural Boundaries

- Summarization and relevance scoring only.
- Must not publish execution intents.

## Coding Conventions

- Keep summarization windows, freshness rules, and confidence metadata explicit.

## Dependency Rules

- Depends on normalized news inputs and LLM gateway (if model-based summarization is used).

## Extension Rules

- New summarization models require quality and latency validation.

## Integration Contracts

- Publishes summary artifacts for market context enrichment.

## Testing Expectations

- Validate freshness, relevance, and fallback behavior under missing data.

## Operational Notes

- Summarizer failures should emit degraded-mode signals, not halt orchestration.
