# Runtime Ops Hotfix Design (Pre-P9-004)

## Scope

Address blocking local/runtime issues before `P9-004..P9-006`:

1. `notification_worker` crash on RabbitMQ queue-not-found.
2. `make migrate-up` local DB reachability failure.
3. `uv run ...worker` and `uv run ...api` not reading `.env`.
4. `uvicorn` missing from project dependencies.
5. `python -m services.notification_service.worker` runpy warning.
6. Compose full-stack bring-up verification.

## Design

- Add shared `.env` loader and invoke it in API settings, notification settings, Telegram loader, migration env, and env-validation script.
- Harden RabbitMQ HTTP consumer:
  - classify poll HTTP failures,
  - auto-declare missing queue once on 404 `queue_not_found`,
  - continue polling instead of crashing worker loop.
- Remove eager `worker` import from `services.notification_service.__init__` via lazy export shim to avoid runpy warning.
- Add `uvicorn` runtime dependency.
- Update migration workflow with Docker Compose fallback path when local DB connection fails.
- Add tests for env loading and RabbitMQ HTTP queue auto-declare behavior.

## Expected Outcomes

- Worker stays alive instead of exiting on missing queue.
- Local CLI commands respect `.env` without manual `source`.
- API run command can import/run uvicorn.
- Compose profiles can start cleanly with notification worker.
