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
- `docs/market_ingestion_foundation.md` (module architecture and contracts)
- `docs/learning/2026-02-14-p2-ingestion-instincts.md` (continuous-learning-v2 notes)

Runtime verification evidence:

- `docs/runtime/runtime-verification-2026-02-14.md`
