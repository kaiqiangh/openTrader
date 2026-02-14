# openTrader

Auto AI Trading System in Crypto Market

## Development Bootstrap

1. Install `uv`
2. Create `.env` from `.env.example`
3. Run `make env-validate`
4. Run `make test`

## Local Setup (Terminal)

Use this sequence from the project root:

1. Verify Python and uv:

- `python3 --version` (expect `3.13.x` or compatible)
- `uv --version`

2. Sync dependencies into `.venv`:

- `uv sync --all-groups`

3. Validate env keys:

- `cp .env.example .env` (first time only)
- `make env-validate`

4. Run tooling through uv:

- `uv run ruff check .`
- `uv run pytest -q`

5. Run Go tests for real execution service:

- `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`

### Why It Can Work In Codex But Fail Locally

- This Codex environment runs commands in an isolated sandbox with preconfigured paths and tool shims.
- Locally, your shell may not resolve the same binaries/interpreter (`python`, `uv`, `ruff`, `pytest`) unless your PATH and virtual environment are configured.
- In this repo, `ruff` and `pytest` should be run via `uv run ...` so they use project-managed dependencies from `.venv`.

### Troubleshooting `ruff` / `pytest` Locally

1. `uv: command not found`:

- install uv: [https://docs.astral.sh/uv/getting-started/installation/](https://docs.astral.sh/uv/getting-started/installation/)
- restart terminal and re-check `uv --version`

2. `ruff: command not found` or `pytest: command not found`:

- use `uv run ruff check .` and `uv run pytest -q` (not global binaries)
- if needed: `uv sync --all-groups --reinstall`

3. Wrong Python interpreter:

- `which python3`
- `python3 --version`
- ensure compatible version, then run `uv sync`

4. Go cache permission errors:

- run tests with writable cache: `GOCACHE=/tmp/go-build go test ./...`

5. Still failing:

- remove local venv and resync:
  - `rm -rf .venv`
  - `uv sync --all-groups`

6. `async def functions are not natively supported` in pytest:

- ensure dev dependencies are installed: `uv sync --all-groups`
- verify plugin availability: `uv run python -c "import pytest_asyncio; print(pytest_asyncio.__version__)"`

## Infrastructure Foundation

The Phase 1 baseline is configured with Docker Compose:

- PostgreSQL + TimescaleDB (`postgres_timescaledb`)
- Redis (`redis`)
- RabbitMQ (`rabbitmq`)

Useful commands:

1. `docker compose up -d postgres_timescaledb redis rabbitmq`
2. `docker compose ps`
3. `make migrate-up`
4. `make migrate-revision MSG='create_initial_tables'`

Initial migration files:

- `migrations/versions/20260214_0001_core_trading_schema.py`
- `migrations/versions/20260214_0002_timeseries_schema.py`
- `migrations/versions/20260214_0003_agent_trace_schema.py`
- `migrations/versions/20260214_0004_llm_governance_schema.py`
- `migrations/versions/20260214_0005_news_schema.py`

RabbitMQ topology declaration:

- `config/rabbitmq/topology.json` (exchanges, queues, DLQs, bindings)
- `config/contracts/message_envelope.schema.json` (canonical event envelope schema)
- `services/shared/contracts/message_envelope.py` (envelope validator)

Redis keyspace strategy:

- `config/redis/namespaces.json` (machine-readable namespace/TTL spec)
- `docs/redis_namespace_strategy.md` (operator guide)

Phase 2 market ingestion foundation:

- `services/market_ingestion/exchange_adapter.py` (CCXT-style adapter + snapshot bootstrap)
- `services/market_ingestion/connection_resilience.py` (heartbeat/reconnect/backoff manager)
- `services/market_ingestion/order_book_sync.py` (snapshot + delta sync engine)
- `services/market_ingestion/gap_detection.py` (sequence gap classification and resync signaling)
- `services/market_ingestion/kline_validator.py` (k-line continuity and quality validation)
- `services/market_ingestion/canonical_pipeline.py` (canonical normalization + envelope-validated publisher)
- `services/market_ingestion/persistence_writers.py` (timeseries persistence row writers)
- `services/market_ingestion/pipeline_metrics.py` (ingestion lag/rate/reconnect metrics)
- `services/market_ingestion/integration_harness.py` (fixture replay and deterministic digest verification)
- `docs/market_ingestion_foundation.md` (module architecture and contracts)
- `docs/learning/2026-02-14-p2-ingestion-instincts.md` (continuous-learning-v2 notes)
- `docs/learning/2026-02-14-p2-integrity-instincts.md` (continuous-learning-v2 integrity notes)
- `docs/learning/2026-02-14-p2-delivery-instincts.md` (continuous-learning-v2 delivery notes)

Phase 3 agent runtime baseline:

- `services/agent_orchestrator/contracts.py` (shared planner/risk/orchestration contracts)
- `services/agent_orchestrator/orchestrator.py` (market.canonical consumer and decision lifecycle manager)
- `services/agent_orchestrator/planner_agent.py` (dynamic planning from market context and thresholds)
- `services/agent_orchestrator/risk_agent.py` (pre-trade risk signal evaluation and approvals)
- `services/agent_orchestrator/execution_decision_agent.py` (final constrained action proposal generation)
- `services/agent_orchestrator/market_context_agent.py` (optional microstructure/news enrichment before planning)
- `services/agent_orchestrator/guardrail_validation.py` (final schema/risk/symbol/leverage guardrail validation before intent publish)
- `services/agent_orchestrator/memory_layer.py` (short-term Redis-style and long-term Postgres-style decision memory integration)
- `services/agent_orchestrator/replay_service.py` (deterministic reconstruction of decision graph and persisted payloads)
- `services/agent_orchestrator/metrics_tracing.py` (agent stage latency/failure instrumentation plus LLM token/cost telemetry aggregation)
- `docs/agent_runtime_baseline.md` (runtime architecture and lifecycle contract guide)
- `docs/learning/2026-02-14-p3-agent-runtime-instincts.md` (continuous-learning-v2 agent-runtime notes)
- `docs/learning/2026-02-14-p3-execution-decision-instincts.md` (continuous-learning-v2 execution-decision notes)
- `docs/learning/2026-02-14-p3-market-context-instincts.md` (continuous-learning-v2 market-context notes)
- `docs/learning/2026-02-14-p3-guardrail-instincts.md` (continuous-learning-v2 guardrail-validation notes)
- `docs/learning/2026-02-14-p3-memory-layer-instincts.md` (continuous-learning-v2 memory-layer integration notes)
- `docs/learning/2026-02-14-p3-replay-service-instincts.md` (continuous-learning-v2 replay-service notes)
- `docs/learning/2026-02-14-p3-metrics-tracing-instincts.md` (continuous-learning-v2 metrics/tracing notes)

Phase 3 LLM gateway baseline:

- `services/llm_gateway/contracts.py` (typed provider/request/response contracts)
- `services/llm_gateway/gateway.py` (provider timeout/retry/fallback orchestration)
- `services/llm_gateway/persistence.py` (full prompt/response call-record persistence boundary)
- `services/llm_gateway/quota.py` (daily token and monthly cost hard-limit quota contracts)
- `docs/llm_gateway_baseline.md` (gateway architecture and contract guide)
- `docs/learning/2026-02-14-p3-llm-gateway-instincts.md` (continuous-learning-v2 gateway notes)
- `docs/learning/2026-02-14-p3-llm-persistence-instincts.md` (continuous-learning-v2 prompt-response persistence notes)
- `docs/learning/2026-02-14-p3-llm-quota-instincts.md` (continuous-learning-v2 quota enforcement notes)

LLM env notes:

- `LITELLM_BASE_URL`, `LITELLM_API_KEY`, and `LITELLM_TIMEOUT_SECONDS` are consumed by openTrader runtime modules.
- `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` are optional upstream credentials for the LiteLLM deployment and are not directly read by openTrader runtime today.

API auth env notes:

- `JWT_SECRET_KEY` is required for FastAPI bearer-token verification.
- `JWT_ISSUER` and `JWT_AUDIENCE` are optional and default to `open-trader` and `open-trader-api`.

Runtime integration gate + Phase 4 foundations:

- `services/shared/runtime/broker.py` (concrete in-process topic broker adapter)
- `services/market_ingestion/binance_http_adapter.py` (concrete Binance depth transport adapter)
- `services/workers/runtime_pipeline.py` (market->orchestrator runtime worker cycle)
- `services/market_ingestion/sqlalchemy_store.py` (concrete local timeseries persistence adapter)
- `services/agent_orchestrator/sqlalchemy_memory_store.py` (concrete short/long-term memory adapters)
- `services/llm_gateway/sqlalchemy_stores.py` (concrete LLM call/quota persistence adapters)
- `services/llm_gateway/litellm_http_adapter.py` (concrete LiteLLM HTTP provider adapter)
- `services/simulation_execution/mode_routing.py` (`P4-001` strict mode routing policy)
- `services/simulation_execution/engine.py` (`P4-002` simulation fill/slippage/fee core)
- `services/simulation_execution/safety_guard.py` (`P4-003` MOCK-mode live-endpoint safety guard)
- `services/simulation_execution/worker.py` (mock intent consumer -> OMS event publisher)
- `services/simulation_execution/metrics_tracing.py` (`P4-007` execution metrics/tracing for mock worker)
- `docs/runtime/runtime-integration-gate-2026-02-14.md` (runtime gate verification evidence)

Real execution Go baseline (`P4-004`/`P4-005`/`P4-006`):

- `services/real_execution_go/internal/consumer/contracts.go` (queue consumer interface and delivery contract)
- `services/real_execution_go/internal/service/runner.go` (queue poll loop with ack/nack handling)
- `services/real_execution_go/internal/metrics/collector.go` (`P4-007` real runner metrics/tracing collector)
- `services/real_execution_go/internal/service/envelope.go` (REAL-mode execution intent envelope decoder/validator)
- `services/real_execution_go/internal/service/handler.go` (bridge command mapping and idempotent dispatch flow)
- `services/real_execution_go/internal/bridge/contracts.go` (Go<->Python execution bridge command/result contracts)
- `services/real_execution_go/internal/idempotency/store.go` (in-memory dedupe store for create/cancel dispatch)
- `docs/real_execution_go_baseline.md` (architecture and validation notes for real execution skeleton)

OMS lifecycle + risk baseline (`P5-001`..`P5-007`):

- `services/oms/state_machine.py` (explicit order-state transition matrix with idempotent replay handling)
- `services/oms/fill_reconciliation.py` (`P5-002` queue + exchange fallback fill reconciliation)
- `services/oms/position_engine.py` (`P5-003` position netting and realized PnL updates from fills)
- `services/oms/portfolio_snapshot.py` (`P5-004` NAV/unrealized/realized snapshot builder)
- `services/oms/risk_rules.py` (`P5-005` core limits: position/notional/leverage checks)
- `services/oms/risk_guards.py` (`P5-006` portfolio guards: drawdown and daily-loss thresholds)
- `services/oms/risk_controls.py` (`P5-007` circuit-breaker + kill-switch emergency controls)
- `services/oms/risk_policy.py` (composed OMS risk policy evaluator across rules/guards/controls)
- `services/oms/risk_observability.py` (`P5-008` risk telemetry and severity-classified policy/control events)

News pipeline baseline (`P6-001`..`P6-007`):

- `services/news_ingestion/source_connectors.py` (`P6-001` pluggable RSS/API/social connector contracts + registry + resilient fetch-cycle runner)
- `services/news_ingestion/ingestion_service.py` (`P6-002` normalize + dedupe + persistence boundary for news items)
- `services/news_ingestion/tagging_relevance.py` (`P6-003` symbol/topic tagging with relevance and sentiment scoring)
- `services/news_summarizer/summarizer_service.py` (`P6-004` rolling summary generation per symbol/global scope)
- `services/news_summarizer/context_injection_bridge.py` (`P6-005` summary context envelope publisher + market payload injection helper)
- `services/news_summarizer/resilience.py` (`P6-006` stale/missing summary fallback policy with alert envelope publisher)
- `services/news_ingestion/quality_metrics.py` (`P6-007` coverage/freshness/lag/error metric snapshot contracts for news ops visibility)

API control-plane baseline (`P7-001`..`P7-012`):

- `services/api/app.py` (`P7-001` FastAPI app factory, lifespan wiring, and router registration)
- `services/api/settings.py` (`P7-001` API settings contract for mode/auth defaults)
- `services/api/auth.py` (`P7-001`/`P7-002` JWT bearer validation and role-gated dependencies)
- `services/api/state.py` (`P7-001`/`P7-003` in-memory control-plane and trading-ops state adapters)
- `services/api/models.py` (`P7-001`/`P7-003` typed request/response schemas)
- `services/api/routers/system.py` (`P7-001` liveness/readiness and metadata endpoints)
- `services/api/routers/control.py` (`P7-001`/`P7-002` mode and strategy control endpoints with RBAC)
- `services/api/routers/ops.py` (`P7-003` orders/positions/portfolio/risk status and circuit-breaker/kill-switch controls)
- `services/api/routers/governance.py` (`P7-004` LLM usage/quota/breach governance endpoints)
- `services/api/routers/replay.py` (`P7-005` replay request lifecycle and decision replay endpoints)
- `services/api/routers/dashboard.py` (`P7-006` HTML dashboard shell for status/governance/replay pages)
- `services/api/routers/control.py` (`P7-009` mode history API: `GET /control/mode/history`)
- `services/api/routers/ops.py` (`P7-010` news panel APIs: `/ops/news/items`, `/ops/news/summaries`, `/ops/news/impact`)
- `services/api/routers/dashboard.py` (`P7-010` dashboard news panel route: `/dashboard/news`)
- `services/api/static/dashboard_app.js` (`P7-007`/`P7-008`/`P7-009`/`P7-010` React UI module for governance/replay/mode/news views)
- `services/api/static/dashboard.css` (`P7-007`/`P7-008`/`P7-009`/`P7-010` dashboard styling and list rendering performance hints)

Notification runtime baseline (`P7-011`/`P7-012`):

- `services/notification_service/models.py` (typed notification events/preferences/messages/results)
- `services/notification_service/event_intake.py` (source envelope normalization and severity classification)
- `services/notification_service/policy_router.py` (preference filtering, dedupe window, and rate-limit enforcement)
- `services/notification_service/gateway_dispatch.py` (gateway abstraction, delivery attempts, and DLQ capture)
- `services/notification_service/service.py` (`event_intake -> policy_router -> gateway_dispatch` runtime pipeline)
- `services/notification_service/publishers.py` (strategy/OMS/risk/system source-event bridge into `notify.events.raw`)

Runtime verification evidence:

- `docs/runtime/runtime-verification-2026-02-14.md`
