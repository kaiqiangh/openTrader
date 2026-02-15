# P9 Release Checklist (2026-02-15)

## 1. Preflight (All Must Be Green)

- [ ] `uv run ruff check .` passes.
- [ ] `uv run pytest -q` passes.
- [ ] `make smoke` passes with all expected services running.
- [ ] `P9-001..P9-009` statuses are `DONE` in `docs/IMPLEMENTATION_PLAN.md`.
- [ ] Runtime evidence docs exist for validation, replay, performance, resilience, integrity, and security.

## 2. Configuration and Secrets Verification

- [ ] `.env` validated via `make env-validate`.
- [ ] `JWT_SECRET_KEY` is set and non-placeholder.
- [ ] `ENCRYPTION_KEY_BASE64` decodes to 32 bytes.
- [ ] Notification secrets (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_DEFAULT_CHAT_ID`) are non-placeholder when Telegram is enabled.
- [ ] No secrets committed in repository-tracked files.

## 3. Runtime and Infrastructure Readiness

- [ ] `docker compose up -d` brings up all required services.
- [ ] `docker compose ps` reports healthy/running status for critical components.
- [ ] API `/metrics` is reachable and emits Prometheus-format metrics.
- [ ] Notification worker startup validation passes.
- [ ] Migration path verified (`make migrate-up`) or documented fallback used.

## 4. Operational Gate

- [ ] On-call owners assigned for rollout window.
- [ ] Rollback owner and communication channel confirmed.
- [ ] Hypercare monitoring window scheduled (minimum 24 hours).
- [ ] Alerting routes verified (exchange, risk, quota, integrity, notification failure).

## 5. Go/No-Go Sign-Off

- [ ] Engineering lead approval.
- [ ] Operations lead approval.
- [ ] Risk/compliance approval.
- [ ] Final go-live timestamp recorded.
