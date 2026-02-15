# Market Fetch Mode and Real-Data Workflow Instincts (2026-02-15)

## Context

- Objective: add runtime-selectable market data fetch mode (`rest`/`websocket`) with REST default and upgrade mock realtime workflow to use live exchange/news data while preserving mock execution.
- Scope: market ingestion adapter contracts, runtime worker cadence behavior, and workflow script validation semantics for LiteLLM/DeepSeek.

## Instincts Captured

1. Deterministic local validation needs explicit low-noise data cadence
- Signal: high-frequency feed behavior made local testing hard to follow.
- Action: default runtime market fetch mode to REST with explicit poll cadence (`MARKET_DATA_REST_POLL_SECONDS=300`) and keep websocket mode configurable.
- Confidence: high

2. Runtime-critical path and test harness path need controlled separation
- Signal: switching workers to concrete exchange clients can accidentally make unit tests network-dependent.
- Action: keep strict runtime path concrete when `RUNTIME_REQUIRE_DATABASE=true`, but retain synthetic fallback for non-runtime/test harness paths.
- Confidence: high

3. “Mock workflow” should still exercise real upstream context where possible
- Signal: hardcoded market/news payloads reduced confidence in exchange/news integration.
- Action: publish market events from live Binance/Bitget REST orderbooks and enrich with live RSS news context while keeping order execution path mock-only.
- Confidence: high

4. Strict probes must be opt-out, not opt-in, for integration realism
- Signal: best-effort fallback can mask LLM misconfiguration in go-live checks.
- Action: enforce strict LiteLLM/DeepSeek and real-news checks by default in the workflow script, with explicit fallback flags (`--allow-mock-llm`, `--allow-mock-news`).
- Confidence: medium

5. Docs must show operator-visible entrypoints, not just module references
- Signal: users could not easily tell how to open the frontend dashboard.
- Action: README now includes explicit frontend URL/start/open guidance and token expectations for dashboard pages.
- Confidence: high

## Follow-up Hooks

- Add websocket-native exchange clients and parity tests so `MARKET_DATA_FETCH_MODE=websocket` is transport-concrete, not interface-level only.
- Add smoke assertions that workflow events include non-empty live news item payloads and exchange-derived top-of-book values.
- Expose market fetch mode and poll cadence in dashboard status telemetry for operator observability.
