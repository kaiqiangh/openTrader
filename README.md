# openTrader
Auto AI Trading System in Crypto Market

## Development Bootstrap

1. Install `uv`
2. Create `.env` from `.env.example`
3. Run `make env-validate`
4. Run `make test`

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
- `docs/agent_runtime_baseline.md` (runtime architecture and lifecycle contract guide)
- `docs/learning/2026-02-14-p3-agent-runtime-instincts.md` (continuous-learning-v2 agent-runtime notes)
- `docs/learning/2026-02-14-p3-execution-decision-instincts.md` (continuous-learning-v2 execution-decision notes)
- `docs/learning/2026-02-14-p3-market-context-instincts.md` (continuous-learning-v2 market-context notes)

Phase 3 LLM gateway baseline:

- `services/llm_gateway/contracts.py` (typed provider/request/response contracts)
- `services/llm_gateway/gateway.py` (provider timeout/retry/fallback orchestration)
- `docs/llm_gateway_baseline.md` (gateway architecture and contract guide)
- `docs/learning/2026-02-14-p3-llm-gateway-instincts.md` (continuous-learning-v2 gateway notes)

Runtime verification evidence:

- `docs/runtime/runtime-verification-2026-02-14.md`
