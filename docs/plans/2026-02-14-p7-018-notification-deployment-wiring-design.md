# Phase 7 Notification Deployment + Config Wiring Design (P7-018)

## Scope

Implement `P7-018` for notification stack deployability:

- startup configuration validation for notification worker runtime
- docker compose wiring for notification worker process
- env contract and secrets documentation updates

## Current Baseline

- Notification runtime modules, Telegram gateway, observability, and test suite are in place.
- `docker-compose.yml` currently provisions infra services only (`postgres_timescaledb`, `redis`, `rabbitmq`).
- No dedicated notification worker entrypoint currently validates config and consumes notification queue events.

## Design

### 1) Notification worker runtime and startup validation

- Add `services/notification_service/settings.py`:
  - typed worker settings dataclass
  - env parser with strict validation (`NOTIFY_*`, queue/backend, retry/backoff bounds, gateway constraints)
  - explicit startup errors for missing Telegram secrets when Telegram gateway is enabled
- Add `services/notification_service/worker.py`:
  - consumer abstraction
  - in-memory broker consumer for deterministic tests
  - RabbitMQ HTTP API polling consumer for compose runtime baseline
  - CLI entrypoint with `--validate-only` and loop controls

### 2) Compose and env wiring

- Update `.env.example` with missing notification deployment keys:
  - `NOTIFY_ENABLED`, `NOTIFY_QUEUE_NAME`, backend selection, HTTP API URL/timeouts, idle/observability settings.
- Update `scripts/validate_env.py`:
  - include required notification keys
  - enforce conditional Telegram secret requirements when enabled.
- Update `docker-compose.yml`:
  - add `notification_worker` service
  - depend on RabbitMQ health
  - run worker with startup validation via Python module entrypoint

### 3) Docs and contracts

- Update README with:
  - notification worker validation command
  - compose command for notification profile
  - secrets handling notes
- Update AGENT docs for notification and worker operational boundaries.

## Validation Plan

- Add deployment-focused tests:
  - settings validation paths (enabled/disabled + telegram secret guards)
  - in-memory worker consume/process cycle
  - compose/env wiring assertions
- Run full regressions after targeted tests.
