# Agent Runtime Baseline (P3-001..P6-001)

This document defines the first Phase 3 decision runtime modules:

- `services/agent_orchestrator/contracts.py` (`P3-001`/`P3-002`/`P3-003`/`P3-004`/`P3-005`)
- `services/agent_orchestrator/orchestrator.py` (`P3-001`)
- `services/agent_orchestrator/planner_agent.py` (`P3-002`)
- `services/agent_orchestrator/risk_agent.py` (`P3-003`)
- `services/agent_orchestrator/execution_decision_agent.py` (`P3-004`)
- `services/agent_orchestrator/market_context_agent.py` (`P3-005`)
- `services/llm_gateway/gateway.py` (`P3-006`)
- `services/llm_gateway/persistence.py` (`P3-007`)
- `services/llm_gateway/quota.py` (`P3-008`)
- `services/agent_orchestrator/guardrail_validation.py` (`P3-009`)
- `services/agent_orchestrator/memory_layer.py` (`P3-010`)
- `services/agent_orchestrator/replay_service.py` (`P3-011`)
- `services/agent_orchestrator/metrics_tracing.py` (`P3-012`)
- `services/shared/runtime/broker.py` (runtime integration gate)
- `services/workers/runtime_pipeline.py` (runtime integration gate)
- `services/market_ingestion/binance_http_adapter.py` (runtime integration gate)
- `services/market_ingestion/sqlalchemy_store.py` (runtime integration gate)
- `services/agent_orchestrator/sqlalchemy_memory_store.py` (runtime integration gate)
- `services/llm_gateway/sqlalchemy_stores.py` (runtime integration gate)
- `services/llm_gateway/litellm_http_adapter.py` (runtime integration gate)
- `services/simulation_execution/mode_routing.py` (`P4-001`)
- `services/simulation_execution/engine.py` (`P4-002`)
- `services/simulation_execution/safety_guard.py` (`P4-003`)
- `services/simulation_execution/worker.py` (`P4-002`/`P4-003`)
- `services/simulation_execution/metrics_tracing.py` (`P4-007`)
- `services/oms/state_machine.py` (`P5-001`)
- `services/oms/fill_reconciliation.py` (`P5-002`)
- `services/oms/position_engine.py` (`P5-003`)
- `services/oms/portfolio_snapshot.py` (`P5-004`)
- `services/oms/risk_rules.py` (`P5-005`)
- `services/oms/risk_guards.py` (`P5-006`)
- `services/oms/risk_controls.py` (`P5-007`)
- `services/oms/risk_policy.py` (`P5-005`/`P5-006`/`P5-007`)
- `services/oms/risk_observability.py` (`P5-008`)
- `services/news_ingestion/source_connectors.py` (`P6-001`)

## Component Boundaries

1. `contracts.py`
- Shared dataclasses for strategy configuration, planner outputs, risk outputs, execution decisions, market context outputs, and orchestration results.
- Keeps planner/risk/orchestrator interfaces explicit and deterministic.

2. `planner_agent.py`
- Produces a deterministic trade plan from top-of-book context and strategy thresholds.
- Computes orderbook imbalance and emits action (`BUY`/`SELL`/`HOLD`), confidence, and target quantity.

3. `risk_agent.py`
- Evaluates pre-trade risk checks over planner outputs:
  - confidence minimum
  - actionable quantity
  - notional limit
  - position limit
  - drawdown limit
- Returns structured pass/fail signals with `blocked_by` and a normalized risk score.

4. `orchestrator.py`
- Consumes canonical market envelopes (`market.canonical.*`) and validates message envelope schema.
- Builds enriched market context, invokes planner -> risk -> execution decision, and tracks lifecycle events.
- Publishes approved intents through strict mode-routing policy:
  - `execution.intent.mock` for `mode=MOCK`
  - `execution.intent.real` for `mode=REAL`
- Emits lifecycle envelopes to `strategy.decision.lifecycle`.

5. `execution_decision_agent.py`
- Converts planner+risk outputs into constrained proposals:
  - action is always one of `BUY`/`SELL`/`HOLD`/`CLOSE`
  - quantity sign is normalized by action semantics
  - rejected risk paths produce `HOLD` with zero quantity.

6. `market_context_agent.py`
- Enriches canonical market payloads with optional context:
  - microstructure metrics (`spread_bps`, `orderbook_imbalance`, regime)
  - news summary/sentiment fallback handling
  - context quality flags (`has_orderbook`, `has_news`, `context_score`).

7. `llm_gateway/gateway.py`
- Centralized provider routing contract for model calls with:
  - per-provider timeout controls
  - bounded retry policy
  - ordered fallback across providers.
- Runtime integration with planner/risk/execution agents is deferred to follow-up tasks while contract and reliability behavior are now established.

8. `llm_gateway/persistence.py`
- Defines immutable `LLMCallRecord` and storage boundary `LLMCallStore`.
- Captures full prompt/response payloads plus token/cost/latency metadata for successful and terminal failure gateway outcomes.

9. `llm_gateway/quota.py`
- Defines hard-limit quota contracts (`QuotaLimits`, `QuotaUsage`, `LLMQuotaStore`).
- Gateway now performs pre-dispatch hard-limit enforcement and post-success usage increments, with quota-blocked audit records persisted through call-record infrastructure.

10. `guardrail_validation.py`
- Enforces final decision guardrails across:
  - action/quantity schema semantics
  - symbol constraints
  - confidence threshold
  - risk alignment
  - notional/position/leverage bounds.
- Returns structured `GuardrailValidationResult` with explicit violation codes and details.

11. `memory_layer.py`
- Defines short-term (`Redis`) and long-term (`Postgres`) decision memory contracts.
- Hydrates per-decision memory from short-term slots first, then long-term summary fallback.
- Writes decision-stage slots (`context`, `plan`, `risk`, `execution_decision`, `guardrail`, `status`) and persists final summary records for replay/audit workflows.

12. `replay_service.py`
- Reconstructs decision replay artifacts from persisted trace rows and LLM call records.
- Produces ordered graph nodes/edges across decision trace, agent runs, long-term summary, and LLM calls.
- Emits deterministic replay digest over normalized payloads for audit/debug reproducibility.

13. `metrics_tracing.py`
- Defines in-memory metrics/tracing collector contracts for:
  - stage run counts
  - stage failure rates
  - stage latency aggregates
  - LLM token/cost usage aggregates.
- Supports span-like trace snapshots for stage success/failure events.

14. Runtime integration gate modules
- `shared/runtime/broker.py` provides concrete topic-routing broker behavior for local runtime loops and integration tests.
- `workers/runtime_pipeline.py` wires market ingestion worker -> canonical queue -> orchestrator worker cycle.
- `market_ingestion/binance_http_adapter.py` provides concrete exchange transport for Binance depth payloads.
- concrete persistence adapters in ingestion/memory/llm modules provide executable store implementations for runtime verification.
- `llm_gateway/litellm_http_adapter.py` provides concrete HTTP transport against LiteLLM-compatible endpoints.

15. P4 mode-routing and simulation modules
- `simulation_execution/mode_routing.py` enforces strict mode-to-routing contracts and leakage detection.
- `simulation_execution/engine.py` provides deterministic mock fill engine with slippage and fee model.
- `simulation_execution/safety_guard.py` blocks live-order endpoint usage in MOCK-mode paths.
- `simulation_execution/worker.py` consumes mock intents and publishes OMS order events.
- `simulation_execution/metrics_tracing.py` tracks worker success/failure counters, latency aggregates, and recent trace spans for mock execution stages.

16. P5 OMS lifecycle state machine module
- `oms/state_machine.py` provides explicit allowed transition matrix for `NEW -> ... -> terminal` states.
- Transition application is deterministic and supports idempotent same-state replay handling.
- Invalid transitions are rejected with structured `OMSStateTransitionError` exceptions.

17. P5 OMS reconciliation, position, and portfolio modules
- `oms/fill_reconciliation.py` reconciles queue lifecycle events with exchange snapshot fallback and fill-level dedupe.
- `oms/position_engine.py` applies normalized fill events into netted position state with realized PnL handling.
- `oms/portfolio_snapshot.py` computes mode-tagged NAV and unrealized/realized PnL snapshots from balances + marked positions.

18. P5 OMS risk modules
- `oms/risk_rules.py` enforces projected position/notional/leverage limits.
- `oms/risk_guards.py` enforces drawdown and daily-loss account guardrails from portfolio snapshots.
- `oms/risk_controls.py` manages kill-switch and circuit-breaker emergency controls with event records.
- `oms/risk_policy.py` composes core rules, guards, and controls into deterministic allow/deny policy outcomes.

19. P5 risk observability module
- `oms/risk_observability.py` tracks policy evaluation totals, denied reason counters, and severity-classified risk events.
- `RiskPolicyEngine` can emit observability sink callbacks for decision evaluations and drained control events.

20. P6 source connector framework module
- `news_ingestion/source_connectors.py` defines pluggable source connector protocol and registration framework.
- Connector cycle runner isolates per-source failure and returns degraded-source markers without blocking healthy sources.

## Decision Lifecycle

1. `agent.decision.received`
- Market event accepted by orchestrator.

2. `agent.decision.context_enriched`
- Market context enrichment output recorded before planning.

3. `agent.decision.planned`
- Planner output materialized with action/confidence/metrics.

4. `agent.decision.risk_approved` or `agent.decision.risk_rejected`
- Risk checks decide whether execution can proceed.

5. `agent.decision.action_proposed`
- Final constrained action proposal produced and recorded.

6. `agent.decision.guardrail_passed` or `agent.decision.guardrail_rejected`
- Guardrail validation decision recorded with blocked reasons and check matrix.

7. `agent.decision.intent_published` (approved + executable path only)
- Execution intent is emitted to mode-specific queue.

Memory handling notes:
- On cycle start, orchestrator reads decision memory (`redis` preferred, `postgres` fallback).
- During cycle execution, orchestrator writes stage outputs into short-term decision slots.
- On cycle completion, orchestrator persists a long-term decision summary and re-caches summary in short-term memory.

Replay handling notes:
- Replay reads canonical trace metadata from `decision_traces` plus run/message records from `agent_runs`/`agent_messages`.
- Replay merges optional long-term memory summary/lifecycle snapshots and persisted `llm_calls`.
- Replay output is sorted deterministically and hashed for stable verification.

Metrics/tracing notes:
- Orchestrator records latency and status for major runtime stages (`market_context_agent`, `planner_agent`, `risk_agent`, `execution_decision_agent`, `guardrail_validation`) plus memory stages.
- Gateway can emit LLM call metrics (tokens/cost/latency/status) into the same collector for shared runtime observability.

## Contract Notes

- Envelope contract:
  - Every published lifecycle/intent event is validated through `services/shared/contracts/message_envelope.py`.
- Planner contract:
  - Inputs: `best_bid_size`, `best_ask_size`, `mid_price` (+ optional context fields).
  - Outputs: `PlannerDecision(action, confidence, target_quantity, metrics, rationale)`.
- Risk contract:
  - Inputs: planner decision + market context + strategy risk limits.
  - Outputs: `RiskAssessment(approved, signals, blocked_by, risk_score, approved_quantity)`.
- Execution decision contract:
  - Inputs: planner decision + risk assessment + market context.
  - Outputs: `ExecutionDecision(action, quantity, confidence, rationale, constraints)`.
- Market context contract:
  - Inputs: canonical market payload + optional embedded news context.
  - Outputs: `MarketContextOutput(context, microstructure, news, quality, notes)`.
- Memory contract:
  - Short-term store: `write_slot(...)`, `read_slots(...)` for `mem:decision:{mode}:{strategy_id}:{decision_id}:{slot}`.
  - Long-term store: `persist_decision_summary(record)`, `read_decision_summary(decision_id)` for durable decision summaries.
- Replay contract:
  - Trace store: `read_decision_trace(...)`, `list_agent_runs(...)`, `list_agent_messages(...)`, `list_llm_calls(...)`.
  - Result: deterministic `DecisionReplayResult` with graph nodes/edges and replay digest.
- Metrics/tracing contract:
  - Stage metrics: `record_stage_success(...)`, `record_stage_failure(...)`.
  - LLM usage metrics: `record_llm_call(...)`.
  - Snapshot: consolidated stage and LLM telemetry payload for observability surfaces.
- OMS contract:
  - `OMSStateMachine.apply(next_state)` validates lifecycle transitions for `NEW`, `SUBMITTED`, `OPEN`, `PARTIALLY_FILLED`, `FILLED`, `CANCELED`, `REJECTED`, `EXPIRED`.
  - Same-state replay is an idempotent no-op; illegal transitions fail fast.
  - `FillReconciliationEngine.reconcile(...)` produces canonical order status/fill convergence using queue events first with exchange fallback.
  - `PositionEngine.apply_fill(...)` updates signed position quantity, average entry price, and realized PnL from each normalized fill.
  - `PortfolioSnapshotEngine.build_snapshot(...)` emits `portfolio_snapshots`-compatible records (`total_balance_usd`, `available_balance_usd`, `locked_balance_usd`, `unrealized_pnl`, `realized_pnl_today`).
  - `CoreRiskRuleEngine.evaluate(...)` enforces projected position/notional/leverage bounds for each proposed order.
  - `DrawdownDailyLossGuardEngine.evaluate(...)` enforces drawdown and daily-loss guardrails from current account state.
  - `RiskControlPlane` controls circuit-breaker and kill-switch block status with structured control events.
  - `RiskPolicyEngine.evaluate(...)` combines rules + guards + controls into a single policy decision artifact.
  - `RiskObservabilityCollector` records policy/control telemetry snapshots and structured events for downstream alerting and APIs.
- News connector contract:
  - `SourceConnectorRegistry` manages connector discovery/lookup by stable connector IDs.
  - `NewsSourceConnectorFramework.fetch_cycle(...)` executes per-source fetch with fault isolation and normalized cycle summaries.

## Usage Flow

1. Ingest canonical market envelope from queue `market.canonical`.
2. Call `AgentOrchestrator.handle_market_event(envelope, strategy=...)`.
3. Consume orchestration result:
- `status` for decision state.
- `market_context` for enrichment artifacts and quality signals.
- `plan` for planner output.
- `risk` for risk signal breakdown.
- `execution_decision` for constrained final action proposal.
- `execution_intent` when approved.
4. Downstream execution services consume mode-specific execution intent queues.
