# Review Fixes Plan — 2026-03-30

## Context
Post-review fixes for openTrader codebase. Review identified 20+ issues across security, code quality, ARD/PRD alignment, and incomplete work.

## Tasks

### Tier 1 — Critical/High Security (5 items)

- [ ] T1: Timing-vulnerable API key comparison → `hmac.compare_digest` in `services/api/routers/internal.py`
- [ ] T2: Remove HS256 fallback from `services/api/auth.py` + `services/api/settings.py`
- [ ] T3: Fix Postgres & RabbitMQ network isolation in `docker-compose.yml` (remove `public`)
- [ ] T4: Fix notification_worker network in `docker-compose.yml` (remove `public`)
- [ ] T5: Add auth to `/metrics` endpoint in `services/api/routers/system.py`

### Tier 2 — High Code Quality (3 items)

- [ ] T6: Fix `data_retention_cleanup` table names in `services/tasks/workloads.py`
- [ ] T7: Migrate guardrail_validation.py to Decimal (match risk_rules.py)
- [ ] T8: Persist DLQ items to DB in `services/notification_service/gateway_dispatch.py`

### Tier 3 — Medium Security/Quality (4 items)

- [ ] T9: Add JWT refresh token mechanism + short-lived access tokens
- [ ] T10: Input validation regex on API params (symbols, decision_id, strategy_id)
- [ ] T11: Fix Redis URL in .env (remove bare REDIS_URL, keep interpolated form)
- [ ] T12: Add RS256 token generator script, delete archive/generate_token.py

### Tier 4 — Low Priority (3 items)

- [ ] T13: Reduce JWT max lifetime default from 24h to 1h
- [ ] T14: Add Redis-backed rate limiter for multi-instance
- [ ] T15: Implement or remove placeholder Celery tasks from beat schedule

## Verification
- All existing tests must pass (742 Python + 7 Go)
- New code must have tests where applicable
- No regressions in auth/security paths
