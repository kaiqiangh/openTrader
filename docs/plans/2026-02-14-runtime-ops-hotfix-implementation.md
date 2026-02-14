# Runtime Ops Hotfix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove pre-Phase-9 operational blockers affecting notification worker startup, env-loading reliability, migration usability, and API boot commands.

**Architecture:** Keep changes minimal and localized: shared `.env` loader in runtime utilities, worker-level queue auto-heal, lazy package exports to avoid runpy pre-import, and fallback migration execution in Docker network.

**Tech Stack:** Python 3.13, pytest, Docker Compose, Alembic, uv/uvicorn.

---

### Task 1: Shared `.env` runtime loader

- Create `services/shared/runtime/env_loader.py`.
- Wire loader into:
  - `services/api/settings.py`
  - `services/notification_service/settings.py`
  - `services/notification_service/telegram_gateway.py`
  - `migrations/env.py`
  - `scripts/validate_env.py`

### Task 2: Notification RabbitMQ HTTP hardening

- Extend `services/notification_service/worker.py`:
  - add structured poll error type,
  - detect queue-not-found 404,
  - auto-declare queue once, then continue polling.

### Task 3: Module execution warning cleanup

- Refactor `services/notification_service/__init__.py` to lazy-load worker exports via `__getattr__`.

### Task 4: Local runtime tooling fixes

- Add `uvicorn` to `pyproject.toml`.
- Update `Makefile` `migrate-up` with Docker Compose fallback.
- Update docs:
  - `README.md`
  - `docs/notification_worker_deployment.md`

### Task 5: Validation tests

- Add:
  - `tests/test_runtime_env_loading.py`
  - `tests/test_p7_notification_worker_http.py`
- Run:
  - `uv run pytest -q`
  - `uv run ruff check .`
- Verify Compose startup (`notification` + `observability` profiles).
