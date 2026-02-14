# Phase 6 News Runtime Integration Design (P6-005 to P6-007)

## Scope

Deliver the remaining Phase 6 tasks in sequence:

- `P6-005`: context injection bridge from summaries into strategy-context inputs
- `P6-006`: resilience behavior for missing/stale news with alerting
- `P6-007`: news quality metrics snapshots for dashboard/ops use

## Context

- `P6-001`..`P6-004` already provide connector framework, ingestion, tagging, and rolling summary artifacts.
- `MarketContextAgent` already consumes `payload.news` and degrades to `news_unavailable` when missing.
- Message envelope schema and topic broker abstractions are available for publish-side integration.

## Approaches Considered

### Option A (Recommended): Service-level bridge/policy/metrics modules with protocol boundaries

- Add dedicated modules for context publishing/injection, resilience policy, and quality metrics.
- Keep deterministic behavior and in-memory compatibility for unit/integration testing.
- Integrate through envelope-validated events and helper contracts.

Pros:
- Low-risk extension to existing architecture.
- Fast testability with clear boundaries.
- Future dashboard/API integration can reuse existing contracts.

Cons:
- No UI/dashboard surfaces yet (deferred to Phase 7).

### Option B: Fold all functionality into existing summarizer module

Pros:
- Fewer files.

Cons:
- Reduced cohesion and test clarity.
- Harder future extension for alerting and quality telemetry.

### Option C: Build only docs/contracts and defer code

Pros:
- Minimal implementation overhead.

Cons:
- No runnable behavior for resilience/context/quality requirements.

## Selected Design

Option A.

### Module boundaries

- `services/news_summarizer/context_injection_bridge.py`
  - Publish `news.context.summary_ready` envelope to strategy context queue.
  - Inject normalized `news` payload into market payloads for context agent ingestion.

- `services/news_summarizer/resilience.py`
  - Evaluate freshness/unavailability policy for summaries.
  - Produce deterministic fallback payload (`news_unavailable`).
  - Publish `news.resilience.*` alert envelopes when degraded.

- `services/news_ingestion/quality_metrics.py`
  - Track connector, ingestion, summarization, and alert counters.
  - Return snapshot metrics: coverage ratio, error rate, freshness lag, summarization lag.

### Data flow

1. Rolling summary generated from tagged news.
2. Resilience policy evaluates summary freshness/availability.
3. Context bridge publishes strategy context envelope and/or injects `news` payload into market message.
4. Quality metrics capture cycle/ingestion/summary/alert telemetry for dashboard/API consumers.

### Error handling

- Missing publisher surfaces `RuntimeError` for publish paths.
- Stale/missing summary forces fallback payload, never blocks trading pipeline.
- Alert publication is best-effort and contract-validated.

### Testing strategy

- `tests/test_p6_context_injection_bridge.py`: envelope publish and market payload injection.
- `tests/test_p6_news_resilience.py`: missing/stale/fresh behaviors + alert publishing.
- `tests/test_p6_quality_metrics.py`: counters and quality snapshot calculations.
- `tests/test_p6_connector_docs.py`: docs and plan alignment checks.

## Success Criteria

- `P6-005`, `P6-006`, `P6-007` marked `DONE` in `docs/IMPLEMENTATION_PLAN.md`.
- New module tests pass, then full Python + lint + Go checks pass.
- README and runtime docs include new module references and boundaries.
