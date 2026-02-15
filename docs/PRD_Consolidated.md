# Product Requirements Document (PRD)

## LLM-Based Multi-Exchange Crypto Trading System

- Version: 1.1 (Revised)
- Date: 2026-02-15
- Status: Implementation-ready with Phase 10 runtime integration completion

## 1. Executive Summary

This product is a production trading platform for crypto markets that combines real-time exchange data, agent-based LLM decisioning, deterministic risk controls, and automated execution. The system supports both mock trading and real trading, provides full decision observability, and exposes an operations dashboard for portfolio, risk, token usage, and execution monitoring.

## 2. Product Objectives

- Deliver reliable automated trading on Binance and Bitget using real-time market data.
- Support two operating modes: mock trading and real trading.
- Use an agent-based strategy system with memory and guardrails.
- Enforce strict risk controls before every order action.
- Provide full prompt/response traceability and replay for every trade decision.
- Provide governance dashboards for token usage, costs, and quotas.

## 3. Authoritative Technology Baseline

The following decisions are mandatory and final:

- Primary language: Python 3.13+
- Performance-critical services: Go (order execution engine)
- Exchange integration: CCXT Pro
- Message broker: RabbitMQ
- Cache: Redis
- Database: PostgreSQL with TimescaleDB extension
- Non-latency-critical task queue: Celery with Redis broker/backend
- Secrets management: environment variables via `.env` files
- Containerization/deployment: Docker Compose

## 4. Users and Stakeholders

### 4.1 Primary Users

- Trading operators
- Portfolio and risk managers
- Engineering and SRE teams

### 4.2 Stakeholders

- Product leadership
- Security and compliance reviewers
- Trading operations leadership

## 5. Scope

### 5.1 In Scope

- Multi-exchange market data ingestion (Binance, Bitget)
- Agent-based LLM strategy generation
- Mock trading and real trading modes
- Real execution and simulated execution pipelines
- Risk management and circuit breakers
- Portfolio analytics and PnL tracking
- Token usage and LLM governance dashboards
- Prompt/response observability, traceability, and replay
- Crypto news ingestion and strategy context injection
- Extensible operator notification system with Telegram as first gateway

### 5.2 Out of Scope (Current Release)

- DEX trading
- Public external API marketplace
- Mobile-native application

## 6. Functional Requirements

### 6.1 Market Data and Connectivity

- FR-001: System must ingest real-time kline, trade, and order book streams from Binance and Bitget.
- FR-002: System must support reconnect with backoff, stale stream detection, and automatic recovery.
- FR-003: System must initialize order books via REST snapshot and apply ordered deltas.
- FR-004: System must validate and normalize all market events into a canonical schema.
- FR-004A: System must support configurable market delta ingestion mode per runtime (`rest` or `websocket`) without changing downstream contracts.
- FR-004B: Default local/dev runtime mode must be deterministic REST polling with configurable cadence (default recommendation: 5 minutes).

### 6.2 Trading Modes

- FR-005: System must support `MOCK` trading mode using real-time market data and simulated execution.
- FR-006: In `MOCK` mode, no calls are allowed to exchange order endpoints.
- FR-007: System must support `REAL` trading mode with real order placement and lifecycle management.
- FR-008: Mode must be explicit, auditable, and strategy-configurable.

### 6.3 Agent-Based Strategy System

- FR-009: Strategy runtime must be multi-agent and include:
  - Planner Agent
  - Risk Agent
  - Execution Decision Agent
  - Market Context Agent (optional by strategy)
- FR-010: Agent runtime must include short-term memory and long-term memory.
- FR-011: Agent orchestration must support non-rigid execution paths driven by planner outputs and guardrail checks.
- FR-012: All agent outputs must pass schema validation and policy validation before execution.

### 6.4 LLM Governance and Observability

- FR-013: System must provide token usage dashboard with:
  - Per-strategy usage
  - Per-agent usage
  - Daily and monthly aggregates
  - Cost estimates
  - Quota usage and hard-limit status
- FR-014: System must persist full prompts and model responses for every agent call.
- FR-015: System must persist latency, token counts, model/provider identifiers, and trace IDs for each call.
- FR-016: System must support replay of decision traces for audit and debugging.

### 6.5 News Intelligence Module

- FR-017: System must ingest crypto news from curated external sources, including social feeds such as X/Twitter where accessible.
- FR-018: System must persist raw news items and normalized metadata.
- FR-019: System must generate strategy-ready news summaries and inject them into agent context.
- FR-020: News ingestion and summarization failures must not block market ingestion or risk controls.

### 6.6 Execution and OMS

- FR-021: System must support market, limit, stop, take-profit, and OCO workflows where supported by exchange.
- FR-022: OMS must track full lifecycle states and fill reconciliation.
- FR-023: Order handling must be idempotent and safe under retries.
- FR-024: Position and portfolio states must be updated in near real-time from fill events.

### 6.7 Risk Management

- FR-025: System must enforce position limits, per-symbol exposure limits, and leverage validation.
- FR-026: System must enforce max drawdown protection and daily loss limits.
- FR-027: System must enforce circuit breakers and kill switch.
- FR-028: Risk policy checks are mandatory in both `MOCK` and `REAL` modes.

### 6.8 Security and Access

- FR-029: Exchange API keys must be encrypted at rest.
- FR-030: System must enforce network isolation between public and internal services.
- FR-031: If UI is enabled, system must enforce role-based access control.

### 6.9 Notification and Alerting Delivery

- FR-032: System must provide a generalized notification service with pluggable gateway abstraction.
- FR-033: Initial gateway implementation must support Telegram Bot delivery.
- FR-034: Gateway abstraction must support future providers without core pipeline rewrites, including Email, Slack, Webhook, SMS, mobile push, and custom API endpoints.
- FR-035: Notification events must include at minimum:
  - trading signals generated
  - order created / partially filled / filled / canceled / rejected
  - risk triggers (drawdown threshold, liquidation risk, margin alert)
  - strategy state changes (enabled/disabled/paused)
  - exchange connectivity issues and reconnect storms
  - system critical errors and degraded dependencies
  - manual intervention actions (kill switch, forced close, mode override)
- FR-036: Notification events must be classified by severity (`INFO`, `WARNING`, `CRITICAL`) with configurable routing rules per user.
- FR-037: Users must be able to configure notification preferences by:
  - strategy scope
  - event type
  - severity threshold
  - gateway/channel target
  - quiet hours / maintenance suppressions
- FR-038: Notification service must enforce anti-spam controls:
  - per-event deduplication window
  - per-user and per-gateway rate limits
  - burst protection and coalescing for repeated events.
- FR-039: Delivery failures must follow bounded retry policy with backoff, DLQ persistence, and operator-visible failure status.
- FR-040: Critical notification delivery failures must produce secondary internal alerts and audit logs.
- FR-041: UI surfaces must be read-only by default for runtime data access; no direct DB write path is allowed from UI components.

## 7. Non-Functional Requirements

### 7.1 Latency and Performance

- NFR-001: Internal order execution service dispatch latency target: <= 20ms p95.
- NFR-002: End-to-end signal-to-order-request latency target: <= 150ms p95, excluding exchange response time.
- NFR-003: Market event normalization latency target: <= 50ms p95.

### 7.2 Reliability

- NFR-004: Event delivery semantics: at-least-once.
- NFR-005: Availability target: 99.9% for core trading services.
- NFR-006: Automatic failover behavior for transient dependency failures (exchange APIs, LLM provider errors, broker reconnect).

### 7.3 Observability

- NFR-007: Centralized structured logging across all services.
- NFR-008: Metrics collection for system, trading, risk, LLM, and news modules.
- NFR-009: Distributed tracing across ingestion -> agent -> risk -> execution flows.
- NFR-010: Health checks and alerting for all critical services.

### 7.4 Data Integrity

- NFR-011: WebSocket reconnect and state recovery must prevent silent data loss.
- NFR-012: Order book resync and gap detection must be implemented.
- NFR-013: K-line reconstruction validation must detect missing/invalid bars.

### 7.5 Notification Quality

- NFR-014: Critical notifications should be dispatched within 5 seconds p95 from source event ingestion.
- NFR-015: Notification dedupe/rate-limit controls must prevent alert storms during high-volatility bursts.
- NFR-016: Notification delivery attempts and outcomes must be fully auditable.

### 7.6 Runtime Readiness and Deployment

- NFR-017: A single `docker compose up -d` must boot the full local platform topology (data, ingestion, orchestration, execution, news, notification, API, observability) without profile-specific startup commands.
- NFR-018: Production-mode runtime paths must avoid in-memory persistence and in-process broker shims; these are allowed only for tests/dev harnesses.
- NFR-019: End-to-end runtime validation must include real infrastructure dependencies (RabbitMQ + PostgreSQL/TimescaleDB + Redis) and not rely exclusively on contract-only tests.

## 8. Product Data Requirements

Required persisted domains:

- Market data (kline/order book/trades)
- Signals and decision traces
- Orders, fills, positions, portfolio snapshots
- LLM prompts/responses, token and cost metrics
- Agent runs, agent messages, memory snapshots
- News items and summaries
- Notification preferences, event records, delivery attempts, and delivery outcomes

Persistence policy:

- PostgreSQL + TimescaleDB is the system of record for runtime-critical data.
- SQLite/in-memory persistence is allowed only for deterministic local tests/dev harnesses and must not be used for production runtime-critical paths.

## 9. Dashboard Requirements

The UI must include:

- Trading mode status (read-only in current release)
- Portfolio and risk dashboard
- Orders, positions, and fills
- Signal and agent-decision timeline
- Token usage dashboard (strategy, agent, day/month, quota)
- Prompt/response inspector with replay support
- News feed and summary impact panel
- Notification preference management and delivery status timeline

UI access policy:

- UI is read-only by default and should not perform direct persistence mutations.
- Operational write actions remain backend-governed, authenticated API operations.

## 10. Acceptance Criteria

### 10.1 Mode Separation

- `MOCK` mode proves zero exchange order endpoint calls in audit logs.
- `REAL` mode proves full order lifecycle tracking and reconciliation.

### 10.2 Governance

- Token dashboard displays per-strategy and per-agent usage with daily/monthly views.
- Quota enforcement blocks over-limit LLM calls and emits alerts.

### 10.3 Observability and Replay

- Every executed trade links to full agent decision trace, prompts, and responses.
- Decision replay can reconstruct final decision state deterministically from persisted records.

### 10.4 Risk

- Risk controls block violating orders in both modes.
- Circuit breakers and kill switch are validated in staged failure tests.

### 10.5 Notifications

- Notification service publishes and routes required event classes with severity-aware policies.
- Telegram delivery is operational end-to-end with retry and failure visibility.
- Rate limiting and deduplication protections are validated under burst scenarios.
- User preference rules correctly filter/suppress delivery by scope and severity.

### 10.6 Runtime Integration Gate

- System provides a concrete application entry flow from market ingestion through execution and persistence (not only in-memory harness execution).
- RabbitMQ-backed worker paths are validated for both mock and real intent queues.
- TimescaleDB/PostgreSQL persistence is validated for market, OMS, news, and notification audit surfaces.
- Go real-execution runtime uses a concrete queue consumer and bridge adapter in staging validation.

## 11. Delivery Phases

- Phase 1: Core ingestion, data model, mock mode, baseline agents
- Phase 2: Real execution (Go engine), risk hardening, OMS reconciliation
- Phase 3: LLM governance dashboard, full prompt/response replay, news module
- Phase 4: Performance tuning, reliability hardening, operator notifications, and operational readiness

## 12. Final Product Decisions (2026-02-15)

These decisions are now explicit product constraints:

- Market data storage strategy:
  - K-lines and sampled order book snapshots are persisted in TimescaleDB.
  - Raw full-depth WebSocket streams are not persisted end-to-end.
  - Order book snapshots are sampled at configurable interval `X` minutes (default recommendation: 1 minute in prod, 5 minutes in dev).
- Messaging strategy:
  - RabbitMQ is the mandatory inter-service messaging backbone.
  - Direct service-to-service runtime calls across bounded contexts are disallowed on the critical trading path.
- Agent triggering strategy:
  - Hybrid trigger model is required.
  - Primary trigger: event-based on canonical candle close / market-context-ready events.
  - Secondary trigger: low-frequency time watchdog for missed-event recovery and liveness.
- Phase advancement gate:
  - Contract-only test completion is insufficient for readiness.
  - Phase advancement requires real end-to-end runtime validation on concrete infrastructure adapters.
