# CI/CD Pipeline Plan

## Context
openTrader has 768 tests, no CI running them on PRs. Existing `.github/workflows/ci.yml` is broken (missing `uv sync`, no ruff, no coverage). Nightly probe references deprecated `JWT_SECRET_KEY`.

## Scope
Fix and enhance CI pipeline. NOT touching deployment (Railway/AWS) — that's a separate session.

## Tasks

### T0: Fix existing ruff violations (52 errors)
- Run `uv run ruff check . --fix` for auto-fixable issues
- Manually fix remaining E402 import order violations
- Run `uv run ruff format .` to align formatting
- Verify: `uv run ruff check .` returns 0 errors

### T1: Fix ci.yml — Python checks
- **File:** `.github/workflows/ci.yml`
- Fix: add `uv sync --all-groups` before `uv run pytest`
- Add ruff lint step: `uv run ruff check .`
- Add ruff format check: `uv run ruff format --check .`
- Pin Go version to 1.23+
- Add `--tb=short` to pytest for cleaner CI output

### T2: Add coverage gate
- **File:** `.github/workflows/ci.yml`
- Add `uv run pytest --cov=services --cov-report=term-missing --cov-fail-under=60`
- Install `pytest-cov` dependency (add to pyproject.toml dev deps if missing)
- Threshold: 60% (current baseline). Can raise later.

### T3: Add Docker Compose validation
- **File:** `.github/workflows/ci.yml`
- Add job: `docker-check`
- Steps: `docker compose config --quiet` to validate compose syntax
- Optional: `docker compose up -d postgres_timescaledb rabbitmq migrator` then health check, then tear down
- This catches broken compose configs before merge

### T4: Fix nightly-live-probe.yml
- Replace `JWT_SECRET_KEY` with `JWT_PRIVATE_KEY` + `JWT_PUBLIC_KEY` references
- Update Go version 1.22 → 1.23

### T5: Add status badge to README
- Add CI badge at top: `![CI](https://github.com/kaiqiangh/openTrader/actions/workflows/ci.yml/badge.svg)`

## Verification
- Fix 52 existing ruff violations before CI can pass (mostly E402 import order)
- Run `uv run ruff check . && uv run ruff format --check .` locally to confirm
- All 768 tests should pass in CI
- Ruff check should pass with zero errors
