# Repo Alignment Review Gap Analysis

- Generated: 2026-02-16
- Scope docs:
  - `/Users/kai/Desktop/openTrader/docs/ARD_Consolidated.md`
  - `/Users/kai/Desktop/openTrader/docs/PRD_Consolidated.md`
  - `/Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md`
- Branch: `features/repo-alignment-realdata-mockworkflow`

## Current Runtime State

### Docker Compose status snapshot (core default)

Observed via:
- `docker compose --profile full down --remove-orphans`
- `docker compose up -d`
- `docker compose ps`

Core profile (`docker compose up -d`) brings up:
- `postgres_timescaledb` (healthy)
- `rabbitmq` (healthy)
- `redis` (healthy)
- `migrator` (`Exited (0)` as expected one-shot)
- `api`
- `runtime_worker_market`
- `runtime_worker_orchestrator`
- `runtime_worker_simulation`
- `runtime_worker_oms`
- `runtime_worker_news`
- `notification_worker`

Full-only extras are not started in core mode and are available via `docker compose --profile full up -d`:
- `real_execution_go`
- `prometheus`, `alertmanager`, `loki`, `tempo`, `grafana`

### Environment/runtime blockers observed

1. Local `.env` initially missed newly required runtime keys (`MARKET_EXCHANGES`, `MARKET_SYMBOLS`, `ORDERBOOK_SNAPSHOT_INTERVAL_SECONDS`, `KLINE_*`, `NEWS_*`), causing `make env-validate` failure.
2. Default RSS feeds in `.env.example` (`coindesk`, `cointelegraph`) were unreachable from this container network during verification; runtime news mode worked after switching local feed list to reachable real RSS endpoints.
3. Local `.env` `LITELLM_BASE_URL=http://litellm:4000` is not host-reachable for script execution; strict workflow validation succeeded by overriding to a reachable LiteLLM-compatible endpoint (`https://api.deepseek.com`) with real model call.

### Verification snapshot (2026-02-16)

- Strict workflow:
  - `LITELLM_BASE_URL=https://api.deepseek.com LITELLM_MODEL=deepseek-chat uv run python scripts/mock_realtime_workflow_test.py --seed 42 --symbol BTC/USDT --interval 1m`
  - Result: `workflow.ok ...` with persisted decision/trace/mock execution.
- K-lines:
  - `uv run python scripts/verify_klines_persistence.py --symbol BTC/USDT --interval 1m --exchanges binance,bitget --minutes 10`
  - Result: `kline.verify.ok` for both exchanges.
- Orderbooks:
  - `uv run python scripts/verify_orderbook_snapshots.py --symbol BTC/USDT --exchanges binance,bitget --minutes 10 --expected-interval-seconds 180`
  - Result: `orderbook.verify.ok` for both exchanges.
- Persistence counts after strict workflow run:
  - `llm_calls=4`, `decision_traces=12`, `agent_runs=60`, `agent_messages=120`, `decision_news_links=6`
  - `orders=8`, `fills=8`, `positions=1`, `portfolio_snapshots=16`

## Requirement Mapping

| Requirement | Doc reference | Code reference | Status | Fix plan |
|---|---|---|---|---|
| Ingest Binance + Bitget kline/orderbook real data | PRD FR-001/FR-004, ARD 1.2/11.1 | `/Users/kai/Desktop/openTrader/services/workers/main.py`, `/Users/kai/Desktop/openTrader/services/market_ingestion/binance_http_adapter.py`, `/Users/kai/Desktop/openTrader/services/market_ingestion/bitget_http_adapter.py` | ✅ | Implemented multi-exchange loop with kline polling and sampled orderbook persistence |
| Configurable orderbook snapshot interval precedence | ARD 1.2, PRD FR-004B | `/Users/kai/Desktop/openTrader/services/workers/main.py`, `/Users/kai/Desktop/openTrader/scripts/validate_env.py`, `/Users/kai/Desktop/openTrader/.env.example` | ✅ | `ORDERBOOK_SNAPSHOT_INTERVAL_SECONDS` -> fallback `MARKET_DATA_REST_POLL_SECONDS` -> default `180` |
| Real news ingestion in runtime DB-required mode | PRD FR-017..FR-020, ARD 8.x/11.4 | `/Users/kai/Desktop/openTrader/services/workers/main.py` | ✅ | Runtime requires real RSS connectors when DB-required; mock retained for deterministic non-runtime tests |
| Persist full LLM prompts/responses in strict workflow | PRD FR-014/FR-015, ARD 7.2/11.3 | `/Users/kai/Desktop/openTrader/scripts/mock_realtime_workflow_test.py`, `/Users/kai/Desktop/openTrader/services/llm_gateway/sqlalchemy_stores.py` | ✅ | Strict workflow now fails fast on LLM failure and writes `llm_calls` |
| Persist orchestration traces and governance lineage | PRD FR-016, ARD 11.2/11.4 | `/Users/kai/Desktop/openTrader/services/agent_orchestrator/sqlalchemy_trace_store.py`, `/Users/kai/Desktop/openTrader/services/workers/main.py` | ✅ | Wired `decision_traces`, `agent_runs`, `agent_messages`, `decision_news_links` |
| Mock execution persists to canonical trading tables | ARD 11.1/11.5, PRD FR-005/FR-022..FR-024 | `/Users/kai/Desktop/openTrader/services/workers/runtime_persistence.py`, `/Users/kai/Desktop/openTrader/migrations/versions/20260216_0006_runtime_persistence_consolidation.py` | ✅ | Consolidated runtime writes to `orders/fills/positions/portfolio_snapshots`; added `positions.mode` |
| Strict end-to-end real-data + mock-trade workflow script | User deliverable, PRD Section 10 | `/Users/kai/Desktop/openTrader/scripts/mock_realtime_workflow_test.py` | ✅ | Script uses DB context + strict LLM + orchestration + persistence assertions |
| Kline and orderbook persistence verification scripts | User deliverable | `/Users/kai/Desktop/openTrader/scripts/verify_klines_persistence.py`, `/Users/kai/Desktop/openTrader/scripts/verify_orderbook_snapshots.py` | ✅ | Added live DB verification scripts for freshness/cadence/dup checks |
| Compose simplification (core default, full optional) | PRD NFR-017 (updated), ARD 1.1/1.2 | `/Users/kai/Desktop/openTrader/docker-compose.yml`, `/Users/kai/Desktop/openTrader/scripts/smoke_test.py`, `/Users/kai/Desktop/openTrader/scripts/runtime_integration_gate.py`, `/Users/kai/Desktop/openTrader/Makefile` | ✅ | Core services start by default; observability + Go execution under `full` profile |

## DB Table Audit

| Table | Purpose | Writers | Readers | Decision (keep/wire/remove) | Migration action |
|---|---|---|---|---|---|
| `klines` | Canonical kline timeseries | market worker | workflow + analytics | keep/wired | no schema change |
| `orderbook_snapshots` | Sampled depth snapshots | market worker | workflow + analytics | keep/wired | no schema change |
| `decision_traces` | Decision root trace | orchestrator trace store | replay/governance/workflow | keep/wired | no schema change |
| `agent_runs` | Per-stage orchestration runs | orchestrator trace store | replay/governance/workflow | keep/wired | no schema change |
| `agent_messages` | Stage input/output payload logs | orchestrator trace store | replay/governance/workflow | keep/wired | no schema change |
| `llm_calls` | Prompt/response usage governance | LLM gateway store | governance/replay/workflow | keep/wired | no schema change |
| `decision_news_links` | Decision-to-news lineage | orchestrator trace store | replay/workflow | keep/wired | no schema change |
| `orders` | Canonical order lifecycle state | runtime OMS store | ops/workflow/reporting | keep/wired | runtime writers consolidated here |
| `fills` | Canonical fill records | runtime OMS store | ops/workflow/reporting | keep/wired | runtime writers consolidated here |
| `positions` | Canonical position state | runtime OMS store | ops/workflow/reporting | keep/wired | added `mode` column (`MOCK`/`REAL`) |
| `portfolio_snapshots` | Canonical portfolio history | runtime OMS store | ops/workflow/reporting | keep/wired | runtime writers consolidated here |
| `runtime_oms_lifecycle_events` | Operational OMS event log | runtime OMS store | runtime OMS internals/debug | keep | retained as operational table |
| `runtime_oms_mark_prices` | Operational mark-price cache | runtime OMS store | runtime OMS internals | keep | retained as operational table |
| `runtime_oms_orders` | Redundant runtime order table | removed | none | remove | dropped in `20260216_0006` |
| `runtime_oms_positions` | Redundant runtime positions table | removed | none | remove | dropped in `20260216_0006` |
| `runtime_oms_portfolio_snapshots` | Redundant runtime portfolio table | removed | none | remove | dropped in `20260216_0006` |
| `news_summary_sources` | Summary-to-source lineage | news runtime store | workflow/context fetch | keep/wired | normalized name (from runtime-prefixed variant) |

## Implemented Fixes

| Gap | Commit | Verification command |
|---|---|---|
| Baseline alignment report scaffold | `2032f22` | `test -f docs/REVIEW_GAP_ANALYSIS.md` |
| Multi-exchange market persistence (kline + orderbook) | `74eff7b` | `uv run pytest tests/test_binance_http_adapter.py tests/test_bitget_http_adapter.py tests/test_p10_runtime_worker_entrypoints.py -q` |
| Runtime news real RSS mode | `7444799` | `uv run pytest tests/test_p10_runtime_worker_entrypoints.py -q` |
| Trace/governance persistence wiring | `53f88c4` | `uv run pytest tests/test_p10_runtime_worker_entrypoints.py -q` |
| Strict DB-context workflow script | `67b9c56` | `uv run pytest tests/test_mock_realtime_workflow_script.py -q` |
| Runtime persistence consolidation + migration | `2b4cc36` | `DATABASE_URL=postgresql+psycopg://open_trader:change_me@127.0.0.1:5432/open_trader uv run alembic upgrade head && uv run pytest tests/test_runtime_persistence_adapters.py -q` |
| Verification scripts for kline/orderbook | `7043c05` | `uv run pytest tests/test_verify_persistence_scripts.py -q` |
| Compose core/full profile split + gate updates | `9e5e367` | `uv run pytest tests/test_smoke_script.py tests/test_runtime_integration_gate.py tests/test_p8_observability_stack.py -q` |
| Runtime bool upsert fix for exchange/symbol refs | `b55c6cc` | `uv run pytest tests/test_runtime_persistence_adapters.py tests/test_mock_realtime_workflow_script.py -q` |
| Docs alignment across ARD/PRD/plan/README/review | `e8150a0` | `rg -n "core runtime|--profile full|ORDERBOOK_SNAPSHOT_INTERVAL_SECONDS" docs README.md` |
| Security acceptance tests aligned to localhost Postgres exposure policy | `024162f` | `uv run pytest -q` |
