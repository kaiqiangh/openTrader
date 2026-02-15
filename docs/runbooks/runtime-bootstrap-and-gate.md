# Runtime Bootstrap and Integration Gate Runbook

## Purpose

Define the operational bootstrap flow for local/runtime environments and the required validation gates before runtime changes are accepted.

## Prerequisites

- `.env` is present and populated from `.env.example`.
- Docker daemon is available.
- `uv` is installed locally.

## 1) Validate Environment Contract

```bash
make env-validate
```

Expected result:

- `Environment validation passed`

## 2) Bootstrap Full Runtime Topology

```bash
docker compose up -d
docker compose ps -a
```

Expected result:

- Long-running services are `Up`: `api`, runtime workers, `notification_worker`, `real_execution_go`, infra/observability services.
- `migrator` is `Exited (0)` (one-shot migration bootstrap).

## 3) Validate Notification Worker Startup

```bash
uv run python -m services.notification_service.worker --validate-only
```

Expected result:

- Structured log event `notification.worker.startup.validation_passed`

## 4) Run Runtime Integration Gate

```bash
make runtime-gate
```

Expected result:

- Smoke checks pass.
- Targeted Python and Go runtime suites pass.
- Artifact written to `artifacts/runtime_integration_gate/latest.json`.

## 5) Run Deterministic Mocked Realtime Workflow

```bash
make mock-workflow
```

Expected result:

- Script validates market/news/decision/execution/notification/DB flow end-to-end.
- Script temporarily stops `runtime_worker_market` to prevent queue flood during deterministic assertions, then starts it again.

## 6) LiteLLM/DeepSeek Optional Validation

```bash
uv run python scripts/mock_realtime_workflow_test.py --require-litellm
```

Required env:

- `LITELLM_BASE_URL`
- `LITELLM_API_KEY`
- `LITELLM_MODEL` (example: `deepseek/deepseek-chat`)

## 7) Troubleshooting

- `notification.worker.startup.validation_failed` for Telegram:
  - Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_DEFAULT_CHAT_ID`.
- API startup `JWT_SECRET_KEY is required`:
  - Set `JWT_SECRET_KEY` in `.env`.
- Runtime worker DB failures:
  - Verify `POSTGRES_*` / `DATABASE_URL` and ensure `postgres_timescaledb` is healthy.
- Queue backlog impacting deterministic tests:
  - Run `make mock-workflow` (includes queue purge and deterministic sequencing).
