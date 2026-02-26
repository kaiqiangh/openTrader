# Next Dashboard Cutover Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship a standalone Next.js dashboard at `:3000` with full parity to the legacy API-served dashboard while keeping API at `:8000`.

**Architecture:** Build a new client-first Next App Router frontend under `apps/dashboard`, reuse existing API contracts via a typed fetch layer, and enable explicit CORS in FastAPI. Keep legacy dashboard routes as fallback during cutover.

**Tech Stack:** Next.js (App Router, TypeScript), React, SWR-style polling utilities, FastAPI CORS middleware, Docker Compose.

---

### Task 1: Frontend App Scaffold

**Files:**
- Create: `apps/dashboard/package.json`
- Create: `apps/dashboard/tsconfig.json`
- Create: `apps/dashboard/next.config.ts`
- Create: `apps/dashboard/next-env.d.ts`
- Create: `apps/dashboard/app/layout.tsx`
- Create: `apps/dashboard/app/globals.css`

### Task 2: Shared API + Auth + Polling Utilities

**Files:**
- Create: `apps/dashboard/src/lib/config.ts`
- Create: `apps/dashboard/src/lib/auth.ts`
- Create: `apps/dashboard/src/lib/api.ts`
- Create: `apps/dashboard/src/lib/polling.ts`

### Task 3: Parity Views and Interactive Charts

**Files:**
- Create: `apps/dashboard/src/components/dashboard-shell.tsx`
- Create: `apps/dashboard/src/components/charts/candle-chart.tsx`
- Create: `apps/dashboard/src/components/charts/equity-line-chart.tsx`
- Create: `apps/dashboard/app/page.tsx`
- Create: `apps/dashboard/app/status/page.tsx`
- Create: `apps/dashboard/app/governance/page.tsx`
- Create: `apps/dashboard/app/replay/page.tsx`
- Create: `apps/dashboard/app/mode/page.tsx`
- Create: `apps/dashboard/app/news/page.tsx`
- Create: `apps/dashboard/app/notifications/page.tsx`

### Task 4: API CORS for Standalone Frontend

**Files:**
- Modify: `services/api/settings.py`
- Modify: `services/api/app.py`

### Task 5: Runtime Wiring and Docs

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.gitignore`
- Modify: `README.md`

### Task 6: Validation and Commit

**Steps:**
1. Build Next app (`npm install`, `npm run build`).
2. Run targeted tests for API compatibility.
3. Smoke-check compose config and startup commands.
4. Commit in focused units.
