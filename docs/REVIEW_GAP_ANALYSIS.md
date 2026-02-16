# Repo Alignment Review + Mock-Trade Real-Data Workflow

Date: 2026-02-16  
Scope docs reviewed: `docs/ARD_Consolidated.md`, `docs/PRD_Consolidated.md`, `docs/IMPLEMENTATION_PLAN.md`.

## Current Runtime State

### Entrypoints Identified

- Worker entrypoint: `services/workers/main.py` (`market`, `orchestrator`, `simulation`, `oms`, `news`).
- Mock workflow integration entrypoint: `scripts/mock_realtime_workflow_test.py`.
- Runtime persistence adapters: `services/workers/runtime_persistence.py`.
- Compose runtime startup: `docker-compose.yml`.

### Compose Bring-up Attempt

- Attempted command: `docker compose up -d`.
- Result in this execution environment: `docker: command not found`.
- Implication: runtime service liveness and live DB row growth could not be executed in-container here, so runtime-state conclusions below are based on static code-path validation and script-level checks.

## Requirement-to-Code Gap Table

| Requirement | Doc reference | Code reference | Status | Fix plan |
|---|---|---|---|---|
| Real market data ingestion with persisted orderbook snapshots | ARD (market ingestion + `orderbook_snapshots`), PRD FR-003 | `services/workers/main.py`, `services/workers/runtime_persistence.py` | 🟡 | Added env-driven interval override `ORDERBOOK_SNAPSHOT_INTERVAL_SECONDS` and verification script `scripts/verify_orderbook_snapshots.py`. |
| K-line persistence for Binance + Bitget | ARD data schema (`klines`), PRD persistence requirements | `scripts/mock_realtime_workflow_test.py`, `scripts/verify_klines_persistence.py` | 🟡 | Wired workflow script to persist kline rows for both exchanges from fetched market context; added dedicated verification script. |
| End-to-end real-data + mock-trade workflow includes LLM call persistence | ARD LLM observability, PRD governance/traceability | `scripts/mock_realtime_workflow_test.py`, `services/llm_gateway/gateway.py`, `services/llm_gateway/sqlalchemy_stores.py` | 🟡 | Upgraded workflow script to perform one gateway LLM call from DB-backed context and assert `llm_calls` persistence. |
| Agent decision + risk + mock execution persisted | ARD orchestration + execution + persistence | `services/agent_orchestrator/orchestrator.py`, `services/workers/main.py`, `scripts/mock_realtime_workflow_test.py` | 🟡 | Workflow script now asserts persistence of decision slots/memory, OMS orders, and portfolio snapshots. |
| Compose defaults should prioritize core workflow and reduce non-core startup | Implementation plan runtime simplification objective | `docker-compose.yml` | ✅ | Moved API, real execution bridge, and observability stack to optional `full` profile; core workflow remains lightweight by default. |
| Documentation alignment with actual runtime behavior/config | All three docs + README | `README.md`, addenda in ARD/PRD/Implementation Plan | ✅ | Added alignment notes and new verification commands/vars. |

## DB Table Audit

Focused on runtime-critical tables for “real-data + mock-trading” path.

| Table | Purpose | Writers | Readers | Action |
|---|---|---|---|---|
| `orderbook_snapshots` | sampled top-of-book snapshots | market runtime persistence + workflow script | API/ops queries, workflow checks | Keep; wired verification script. |
| `klines` | normalized candle data for symbol/timeframe | workflow script persistence helper (for validation path) | workflow checks, downstream strategy context | Keep; wired + verified by script. |
| `llm_calls` | prompt/response observability and replay | `LLMGateway` call store | governance/replay paths | Keep; explicitly asserted in workflow script. |
| `runtime_decision_slots` | per-decision context/plan/risk slots | orchestrator memory layer | workflow/tests | Keep; explicitly asserted. |
| `runtime_decision_memory` | persisted decision summary lifecycle | orchestrator memory layer | replay/ops | Keep; explicitly asserted. |
| `runtime_oms_orders` | mock execution order state | OMS worker | ops/workflow checks | Keep; explicitly asserted. |
| `runtime_oms_portfolio_snapshots` | portfolio impact snapshots | OMS worker | ops/workflow checks | Keep; explicitly asserted. |
| `news_items` | normalized real news feed records | news worker | context + ops | Keep; explicitly asserted. |

No destructive removals were applied in this change set; emphasis was wiring/verification of previously under-validated tables.

## Docker Compose Simplification Proposal/Implementation

### Proposal

- Keep default compose startup focused on core path: infra + runtime workers + notification.
- Gate extra services by profile:
  - `--profile full` for API, real execution bridge, and observability stack.

### Implemented

- Added `profiles: ["full"]` to:
  - `api`
  - `real_execution_go`
  - `prometheus`, `alertmanager`, `loki`, `tempo`, `grafana`

## Verification Plan (Operator)

Run after starting stack in a Docker-enabled environment:

1. `uv run python scripts/mock_realtime_workflow_test.py --require-real-market --require-real-news`
2. `uv run python scripts/verify_klines_persistence.py --exchanges binance,bitget --symbols BTC/USDT --interval 1m --lookback-minutes 30 --min-rows 1`
3. `uv run python scripts/verify_orderbook_snapshots.py --exchanges binance,bitget --symbols BTC/USDT --lookback-minutes 30 --min-rows 1`

These checks validate that real market/news inputs are consumed and persistence tables are non-empty while execution remains mock-only.
