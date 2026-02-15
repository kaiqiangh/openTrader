# Notification Worker Deployment Notes

## Scope

This document defines startup config and secret requirements for the notification worker runtime (`services.notification_service.worker`).

## Required Runtime Keys

- `RUNTIME_REQUIRE_DATABASE`
- `NOTIFY_ENABLED`
- `NOTIFY_DEFAULT_GATEWAY`
- `NOTIFICATION_DEFAULT_SEVERITY`
- `NOTIFY_QUEUE_NAME`
- `NOTIFY_CONSUMER_BACKEND`
- `NOTIFY_POLL_TIMEOUT_SECONDS`
- `NOTIFY_IDLE_SLEEP_SECONDS`
- `NOTIFY_RATE_LIMIT_PER_MIN`
- `NOTIFY_DEDUPE_WINDOW_SECONDS`
- `NOTIFY_MAX_ATTEMPTS`
- `NOTIFY_BACKOFF_BASE_SECONDS`
- `NOTIFY_BACKOFF_MULTIPLIER`
- `NOTIFY_BACKOFF_MAX_SECONDS`
- `NOTIFY_GATEWAY_TIMEOUT_SECONDS`
- `NOTIFY_OBSERVABILITY_MAX_RECORDS`

## Backend-Specific Keys

- `rabbitmq_http` backend:
  - `NOTIFY_RABBITMQ_HTTP_API_URL`
  - `RABBITMQ_DEFAULT_USER`
  - `RABBITMQ_DEFAULT_PASS`

## Gateway-Specific Secrets

- `telegram` gateway:
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_DEFAULT_CHAT_ID`

Startup validation rejects placeholder or empty Telegram secrets when notifications are enabled and Telegram is the default gateway.
When launched from project root, worker settings also auto-load `.env` before validation.

## Validation Commands

- Global env contract:
  - `make env-validate`
- Notification worker startup validation only:
  - `uv run python -m services.notification_service.worker --validate-only`
- One-cycle local smoke run (host process):
  - `NOTIFY_CONSUMER_BACKEND=inmemory RUNTIME_REQUIRE_DATABASE=false uv run python -m services.notification_service.worker --once`

Runtime policy:

- When `RUNTIME_REQUIRE_DATABASE=true`, `NOTIFY_CONSUMER_BACKEND=inmemory` is rejected.
- Production runtime should use `rabbitmq_http` consumer backend with RabbitMQ credentials configured.

## Compose Runtime

- `docker compose up -d notification_worker rabbitmq`

The `notification_worker` service depends on RabbitMQ health and reads runtime values from `.env`.
If the configured queue does not exist yet, the worker auto-declares it through RabbitMQ HTTP API and continues polling.

## Observability Baseline

- Worker logs are JSON-structured with correlation keys (`trace_id`, `decision_id`, `order_id`, `strategy_id`, `mode`).
- Worker runtime records Prometheus-style metrics internally:
  - `open_trader_notification_worker_polls_total`
  - `open_trader_notification_worker_process_duration_seconds`
  - `open_trader_notification_delivery_results_total`
- API `/metrics` endpoint exposes control-plane request metrics for scraping during `P8-002` baseline validation.
