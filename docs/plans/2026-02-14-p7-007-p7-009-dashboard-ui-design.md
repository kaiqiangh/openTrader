# Phase 7 Dashboard UI Layer Design (P7-007 to P7-009)

## Scope

Build UI layer tasks on top of existing FastAPI API baseline:

- `P7-007`: token usage dashboard UI.
- `P7-008`: prompt/response inspector UI.
- `P7-009`: trading mode panel UI with mode controls and audit-facing history.

## Constraints

- Current repository has no standalone Next.js/Vite frontend package.
- Existing dashboard endpoints are server-rendered HTML pages under `services/api/routers/dashboard.py`.
- API auth is JWT bearer and all control/governance/replay routes require authenticated access.

## Approaches Considered

### Option A (Recommended): FastAPI-served React shell (ESM module) + static assets

- Keep FastAPI as single runtime surface.
- Serve a small React module and CSS from `services/api/static/`.
- Render per-page views by `data-view` attribute in HTML shell.

Pros:
- Minimal infrastructure change and no new Node build dependency.
- Directly layers UI on existing authenticated API routes.
- Fastest path to satisfy `P7-007..P7-009` within current project structure.

Cons:
- Less bundling optimization than full Next.js pipeline.

### Option B: Introduce separate Next.js frontend app

Pros:
- Richer frontend architecture and stronger build tooling.

Cons:
- Adds new workspace/tooling/CI complexity not required for current phase scope.

## Selected Design

Use Option A.

### API and state updates

- Add control-plane mode audit endpoint: `GET /control/mode/history`.
- Extend control-plane state to store mode audit entries when mode is changed.

### UI routes

- `/dashboard` -> overview/navigation shell.
- `/dashboard/governance` -> token usage dashboard + breach history (`P7-007`).
- `/dashboard/replay` -> replay request + decision inspector with LLM prompt/response sections (`P7-008`).
- `/dashboard/mode` -> mode display/control + audit history (`P7-009`).
- Keep `/dashboard/status` for compatibility.

### React performance choices (Vercel skill alignment)

- `async-parallel`: parallel data fetching with `Promise.all` for independent calls.
- `bundle-barrel-imports`: direct module imports only; no barrel aggregators.
- `rerender-derived-state-no-effect`: derive view-level aggregates during render.
- `rendering-content-visibility`: apply CSS `content-visibility:auto` for long rows/lists.

### Auth handling

- Read bearer token from local storage (`openTraderJWT`) with explicit UI controls to set/clear.
- Attach token on all API requests.

### Testing

- Add/extend tests for:
  - mode history endpoint behavior.
  - dashboard pages rendering React shell hooks for governance/replay/mode views.
  - docs checks for `P7-007..P7-009` DONE status and new UI assets mentioned.
