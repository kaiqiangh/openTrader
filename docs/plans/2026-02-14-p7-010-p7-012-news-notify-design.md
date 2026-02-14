# Phase 7 News Panel + Notification Runtime Design (P7-010 to P7-012)

## Scope

Deliver the next Phase 7 tasks:

- `P7-010`: News panel UI with stream, rolling summaries, and symbol impact insights.
- `P7-011`: Notification service runtime core (event intake, policy router, gateway dispatch, dedupe/rate-limit skeleton).
- `P7-012`: Event publisher integration from strategy, OMS, risk, and system-health pipelines.

## Current Baseline

- Dashboard React shell is served from FastAPI static assets.
- Governance/replay/mode UI routes and APIs are already live.
- No dedicated notification service module exists yet.
- Existing pipelines already emit rich event envelopes (`strategy.decision.lifecycle`, `oms.order.*`, risk control events, and runtime worker errors).

## Design Decisions

### 1) News panel as API-backed dashboard view (`P7-010`)

- Add API read endpoints for news panel data under `ops`:
  - `GET /ops/news/items`
  - `GET /ops/news/summaries`
  - `GET /ops/news/impact`
- Extend control-plane state with in-memory news items/summaries and impact aggregation helpers.
- Add `GET /dashboard/news` shell route and a React `news` view.

Why:
- Keeps UI on top of explicit API contracts.
- Reuses existing dashboard shell and auth model.
- Avoids introducing separate frontend runtime.

### 2) Notification service module (`P7-011`)

Create `services/notification_service/` with bounded components:

- `event_intake.py`: normalize and severity-classify incoming envelopes.
- `policy_router.py`: preference filtering, dedupe window, per-user/gateway rate limits.
- `gateway_dispatch.py`: pluggable gateway contract, delivery attempts, and DLQ capture.
- `service.py`: orchestration runtime (`intake -> policy -> dispatch`).
- `models.py`: typed records and enums for notification runtime.

Why:
- Mirrors ARD notification architecture while staying provider-agnostic.
- Isolates gateway side effects from policy logic.

### 3) Event publisher integration (`P7-012`)

Create `services/notification_service/publishers.py` bridge and integrate into source pipelines:

- Strategy: `AgentOrchestrator` emits notification-source events for selected lifecycle events.
- OMS: `SimulationExecutionWorker` emits notification-source events from order lifecycle events.
- Risk: `RiskObservabilityCollector` records notification-source envelopes for denied/control events.
- System-health: `MarketIngestionRuntimeWorker` emits connectivity/critical runtime incident notifications on worker exceptions.

Why:
- Preserves source ownership of domain signals.
- Produces consistent notification envelopes without coupling domain modules to concrete gateways.

## Performance and React Rules Applied

- `async-parallel`: news panel fetches independent datasets with `Promise.all`.
- `bundle-barrel-imports`: no barrel imports; direct ESM module references only.
- `rerender-derived-state-no-effect`: derive table/card views from loaded data in render.
- `rendering-content-visibility`: apply row virtualization hints for long list rendering.

## Validation Plan

- Add targeted tests for:
  - News APIs and dashboard news route.
  - Notification intake/policy/dispatch runtime behavior.
  - Event publisher integrations across strategy/OMS/risk/system-health paths.
- Keep full-suite regression green (`pytest`, `ruff`, Go tests).
