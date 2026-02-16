# Repo Alignment Review Gap Analysis

- Generated: 2026-02-16
- Scope docs:
  - `/Users/kai/Desktop/openTrader/docs/ARD_Consolidated.md`
  - `/Users/kai/Desktop/openTrader/docs/PRD_Consolidated.md`
  - `/Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md`
- Branch: `features/repo-alignment-realdata-mockworkflow`

## Current Runtime State

### Docker Compose status snapshot
- `docker compose ps` shows all current services up, including API, runtime workers, Postgres/Timescale, RabbitMQ, Redis, notification worker, real execution Go, and observability services.
- Runtime worker services are active but key product-critical data paths remain partially unwired.

### Environment/runtime blockers observed
- Strict LLM workflow mode fails when LiteLLM endpoint is unreachable or DNS-resolve fails.
- Strict real-news workflow mode is not reliable because runtime news worker currently relies on mock feed behavior in normal loop.

### DB usage snapshot (current)
- Populated:
  - `orderbook_snapshots=9`
  - `runtime_oms_orders=12`
  - `runtime_oms_lifecycle_events=24`
  - `runtime_oms_positions=1`
  - `runtime_oms_portfolio_snapshots=24`
  - `runtime_decision_memory=13`
  - `runtime_decision_slots=56`
  - `news_items=1`
  - `news_tags=1`
  - `news_summaries=1`
- Empty but expected by ARD/PRD runtime:
  - `klines=0`
  - `llm_calls=0`
  - `decision_traces=0`
  - `agent_runs=0`
  - `agent_messages=0`
  - `orders=0`
  - `fills=0`
  - `positions=0`
  - `portfolio_snapshots=0`
  - `decision_news_links=0`

## Requirement Mapping

| Requirement | Doc reference | Code reference | Status | Fix plan |
|---|---|---|---|---|
| Ingest real-time kline + orderbook for Binance and Bitget | PRD FR-001, ARD 1.2/11.1 | `/Users/kai/Desktop/openTrader/services/workers/main.py`, `/Users/kai/Desktop/openTrader/services/market_ingestion/sqlalchemy_store.py` | 🟡 | Add multi-exchange market loop, add kline polling + persistence, keep orderbook persistence for both exchanges |
| Configurable snapshot interval for orderbook | ARD 1.2, PRD FR-004A/FR-004B | `/Users/kai/Desktop/openTrader/services/workers/main.py`, `/Users/kai/Desktop/openTrader/.env.example` | ❌ | Add `ORDERBOOK_SNAPSHOT_INTERVAL_SECONDS` with fallback precedence to `MARKET_DATA_REST_POLL_SECONDS` |
| Mock trading only but real data ingestion | PRD FR-005/FR-006 | `/Users/kai/Desktop/openTrader/services/simulation_execution/*`, `/Users/kai/Desktop/openTrader/services/workers/main.py` | 🟡 | Keep mock execution path; ensure market/news inputs are real by default in core runtime |
| Full prompt/response persistence for agent LLM calls | PRD FR-014/FR-015, ARD 7.2 | `/Users/kai/Desktop/openTrader/services/llm_gateway/*`, `/Users/kai/Desktop/openTrader/scripts/mock_realtime_workflow_test.py` | ❌ | Force at least one real LLM gateway call in workflow script and persist to `llm_calls` |
| Decision trace + replay artifacts persisted | PRD FR-016, ARD 11.2 | `/Users/kai/Desktop/openTrader/services/agent_orchestrator/orchestrator.py` | ❌ | Add SQLAlchemy trace store wiring for `decision_traces`, `agent_runs`, `agent_messages` |
| News ingestion persists raw + summary and links into decision context | PRD FR-017/18/19, ARD 8.1-8.4 and 11.4 | `/Users/kai/Desktop/openTrader/services/workers/main.py`, `/Users/kai/Desktop/openTrader/services/workers/runtime_persistence.py` | 🟡 | Use real RSS connectors in DB-required mode and persist `decision_news_links` during workflow |
| Core mock trade outcomes persisted in canonical trading tables | ARD 11.1, PRD Section 8 | `/Users/kai/Desktop/openTrader/services/workers/runtime_persistence.py`, migrations | ❌ | Consolidate writes from `runtime_oms_*` into `orders`, `fills`, `positions`, `portfolio_snapshots`; retain only non-redundant runtime tables |
| Core workflow runnable from compose defaults with optional extras profile | User requirement + runtime simplification target | `/Users/kai/Desktop/openTrader/docker-compose.yml`, `/Users/kai/Desktop/openTrader/scripts/smoke_test.py` | ❌ | Make core default startup minimal required services; move observability + real execution extras to `full` profile |
| Runtime verification scripts for klines and orderbook cadence | User deliverables | `/Users/kai/Desktop/openTrader/scripts/` | ❌ | Add `verify_klines_persistence.py` and `verify_orderbook_snapshots.py` |

## DB Table Audit

| Table | Purpose | Writers | Readers | Decision (keep/wire/remove) | Migration action |
|---|---|---|---|---|---|
| `klines` | Canonical kline timeseries | not wired in runtime worker | downstream analytics/workflow scripts | wire | no table change; add runtime writer |
| `orderbook_snapshots` | Canonical orderbook snapshots | market worker | workflow scripts | keep | no table change |
| `decision_traces` | Decision trace root | not wired | replay paths | wire | no table change |
| `agent_runs` | Per-agent stage runs | not wired | replay paths | wire | no table change |
| `agent_messages` | Serialized stage payload messages | not wired | replay paths | wire | no table change |
| `llm_calls` | Prompt/response + usage governance | gateway store exists but not used in workflow | governance/replay | wire | no table change |
| `decision_news_links` | Decision to news lineage | not wired | replay/forensics | wire | no table change |
| `orders` | Canonical order state | currently unused in runtime | ops/reporting | wire | may add compatibility columns/indexes if needed |
| `fills` | Canonical fill records | currently unused in runtime | ops/reporting | wire | may add compatibility columns/indexes if needed |
| `positions` | Canonical position state | currently unused in runtime | ops/reporting | wire | add `mode` for MOCK/REAL separation |
| `portfolio_snapshots` | Canonical portfolio history | currently unused in runtime | ops/reporting | wire | no table change expected |
| `runtime_oms_orders` | Duplicate runtime order state | runtime OMS worker | runtime tests | remove after consolidation | migration drop |
| `runtime_oms_lifecycle_events` | Duplicate runtime fill events | runtime OMS worker | runtime tests | remove after consolidation | migration drop |
| `runtime_oms_positions` | Duplicate runtime positions | runtime OMS worker | runtime tests | remove after consolidation | migration drop |
| `runtime_oms_mark_prices` | Runtime mark cache | runtime OMS worker | runtime OMS worker | keep (operational cache) | keep table |
| `runtime_oms_portfolio_snapshots` | Duplicate runtime portfolio snapshots | runtime OMS worker | runtime tests | remove after consolidation | migration drop |
| `runtime_decision_slots` | Short-term memory slots | orchestrator memory layer | orchestrator memory layer | keep | keep table |
| `runtime_decision_memory` | Long-term summary cache mirror | orchestrator memory layer | replay/read-back | keep | keep table |
| `runtime_news_summary_sources` | Summary-to-news source mapping (runtime name) | news summary store | workflow scripts | rename/normalize | migration rename to neutral table name |

## Implemented Fixes

> Baseline snapshot committed before code changes. This section will be updated per commit with hash and verification command.

| Gap | Commit | Verification command |
|---|---|---|
| Baseline gap map created | pending | `test -f /Users/kai/Desktop/openTrader/docs/REVIEW_GAP_ANALYSIS.md` |

