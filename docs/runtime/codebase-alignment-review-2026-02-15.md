# Codebase and Documentation Alignment Review (2026-02-15)

## Scope

Compared implemented code against:

- `docs/PRD_Consolidated.md`
- `docs/ARD_Consolidated.md`
- `docs/IMPLEMENTATION_PLAN.md`

## Severity Summary

### Critical (Red)

1. Runtime entrypoint gap
   - Only `services/notification_service/worker.py` is a concrete long-running Python worker entrypoint.
   - Ingestion/orchestrator/OMS/news runtime loops are mostly exercised via harnesses/tests.
2. Runtime messaging gap
   - Core runtime path heavily uses in-process broker abstraction (`services/shared/runtime/broker.py`) rather than RabbitMQ clients on trading path.
3. Runtime persistence gap
   - Runtime adapters for market, memory, and LLM stores still use SQLite/in-memory boundaries (`services/market_ingestion/sqlalchemy_store.py`, `services/agent_orchestrator/sqlalchemy_memory_store.py`, `services/llm_gateway/sqlalchemy_stores.py`).
4. Real execution integration gap
   - Go service entrypoint remains noop skeleton (`services/real_execution_go/main.go`) with no concrete queue bridge wiring.
5. Compose completeness gap
   - Default compose stack does not launch full runtime trading pipeline services (`docker-compose.yml` currently boots infra + notification + observability subset).

### Important (Yellow)

1. Integrity service boundary exists but implementation is not complete (`services/integrity_service/`).
2. API state is in-memory control-plane state, not durable store-backed (`services/api/state.py`).
3. News ingestion/summarization runtime persistence is not fully infra-backed on critical paths (`services/news_ingestion/ingestion_service.py` in-memory store boundary).
4. Integration tests are strong for contracts and scenarios but mostly infra-mocked/in-memory.

### Nice-to-Have (Green)

1. Expand architecture diagrams to explicitly distinguish current runtime vs target runtime.
2. Add direct runbook links from API endpoints and dashboard routes.
3. Add contributor templates for architecture change proposals and runtime gate evidence.

## Test Coverage Findings

- Strengths:
  - Broad unit and scenario coverage for phase modules.
  - Good failure-path coverage in risk and notification modules.
  - Replay/performance/chaos suites exist for harness-level validation.
- Gaps:
  - RabbitMQ integration tests use in-memory broker abstraction in most runtime paths.
  - PostgreSQL/Timescale integration coverage is limited compared to contract-level tests.
  - End-to-end runtime tests do not yet prove full compose-deployed service interaction across all pipeline services.

## Final Architecture Decisions

1. DB storage strategy
   - TimescaleDB for `klines` and sampled `orderbook_snapshots`.
   - PostgreSQL for transactional domains (orders, fills, positions, traces, news metadata, notifications).
   - No full raw websocket archive persistence.
2. Agent trigger strategy
   - Hybrid model:
     - Primary event trigger on canonical market events (candle close / context-ready).
     - Secondary watchdog timer for missed-event recovery.
3. Messaging strategy
   - RabbitMQ is mandatory for inter-service event flow.
   - Direct service-to-service runtime coupling is not allowed on critical trading path.

## Remediation Plan (Phase 10)

1. Add concrete runtime service entrypoints for ingestion, orchestrator, simulation, OMS, and news workers.
2. Replace in-memory broker usage with RabbitMQ producer/consumer adapters on production paths.
3. Replace SQLite/in-memory runtime stores with PostgreSQL/Timescale adapters.
4. Replace Go noop runtime main with concrete queue consumer + bridge + lifecycle publishing.
5. Extend compose to boot full runtime stack by default.
6. Add infra-backed end-to-end runtime validation gate before release sign-off.
