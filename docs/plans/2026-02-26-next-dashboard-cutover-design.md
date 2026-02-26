# Next Dashboard Cutover Design

## Scope
Replace the API-served static dashboard with a standalone Next.js App Router frontend at `http://localhost:3000`, while keeping FastAPI at `http://localhost:8000`. Preserve full operational parity for existing views (`status`, `governance`, `replay`, `mode`, `news`, `notifications`) and JWT-in-app token handling.

## Goals
- Immediate replacement: operators use the new Next app as the primary UI.
- Full parity now: all existing dashboard workflows stay available.
- Safe cutover: API contracts remain unchanged; no breaking backend route rewrites required.

## Non-Goals
- Backend websocket push migration in this cutover.
- Redesign of auth model (JWT remains manually pasted/stored in browser).
- Removal of legacy dashboard endpoints in this phase.

## Architecture
- New frontend app at `apps/dashboard` (Next.js App Router, TypeScript, client-first pages).
- Shared API client + polling hooks with request dedupe and configurable API base URL.
- Polling interval remains 2 seconds for live status/market/portfolio panels.
- Interactive charts keep hover/click inspection behavior for kline and equity views.
- FastAPI gains CORS config for `localhost:3000` browser access.

## Routing and URL Strategy
- Frontend routes:
  - `/` (home)
  - `/status`
  - `/governance`
  - `/replay`
  - `/mode`
  - `/news`
  - `/notifications`
- API remains unchanged under `:8000`.

## Docker and Local Runtime
- Add `web_dashboard` service in `docker-compose.yml` mapped to `127.0.0.1:3000:3000`.
- Resolve full-profile port collision by remapping Grafana host port to `3001`.

## Data Flow
1. User pastes JWT in app UI.
2. Token stored in `localStorage` and injected into `Authorization` header.
3. Pages poll API endpoints every 2s (where applicable).
4. Responses drive chart/table rendering with resilient partial-failure behavior.

## Reliability and UX
- Keep partial-failure resilience per section; one failing panel does not blank all panels.
- Preserve user-inspection flows with chart crosshair and pinned tooltip states.
- Include API connectivity hints in UI for easier runtime diagnostics.

## Security
- JWT remains client-local only (no server persistence).
- No sensitive token logging in frontend.
- CORS allowlist remains explicit/configurable, not wildcard by default.

## Validation
- Build validation: `npm run build` for `apps/dashboard`.
- API compatibility: targeted FastAPI tests for dashboard and ops endpoints.
- Manual smoke:
  - Open `http://localhost:3000/status`
  - Paste viewer/admin token
  - Verify candles/equity/orderbook/trades/governance/replay/mode/news/notifications load.
