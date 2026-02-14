# Agent Runtime Baseline (P3-001..P3-006)

This document defines the first Phase 3 decision runtime modules:

- `services/agent_orchestrator/contracts.py` (`P3-001`/`P3-002`/`P3-003`/`P3-004`/`P3-005`)
- `services/agent_orchestrator/orchestrator.py` (`P3-001`)
- `services/agent_orchestrator/planner_agent.py` (`P3-002`)
- `services/agent_orchestrator/risk_agent.py` (`P3-003`)
- `services/agent_orchestrator/execution_decision_agent.py` (`P3-004`)
- `services/agent_orchestrator/market_context_agent.py` (`P3-005`)
- `services/llm_gateway/gateway.py` (`P3-006`)

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
- Publishes approved intents to:
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

6. `agent.decision.intent_published` (approved + executable path only)
- Execution intent is emitted to mode-specific queue.

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
