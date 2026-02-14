# Phase 8 Observability Stack + Alert Rules + Key Encryption Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver compose-level observability services, critical alert rules, and encrypted exchange credential storage runtime aligned with ARD security requirements.

**Architecture:** Add deterministic Docker Compose observability services and config assets first, then codify alert rules, then implement AES-256-GCM credential encryption/store boundaries for exchange key persistence.

**Tech Stack:** Docker Compose, Prometheus/Grafana/Loki/Tempo/Alertmanager, Python 3.13, sqlite runtime adapters, pytest, ruff.

---

### Task 1: Add failing tests for P8-004/P8-005/P8-006

**Files:**
- Create: `tests/test_p8_observability_stack.py`
- Create: `tests/test_p8_key_encryption.py`
- Modify: `tests/test_p8_observability_docs.py`

**Step 1: Write failing tests**
- Compose contains observability services and profile wiring.
- Required config files exist and are referenced.
- Alert catalog contains critical rules.
- Encryption codec/store behavior satisfies round-trip and non-plaintext persistence.
- `IMPLEMENTATION_PLAN.md` marks `P8-004..P8-006` as `DONE`.

**Step 2: Run targeted tests and confirm failures**

Run:
- `uv run pytest tests/test_p8_observability_stack.py tests/test_p8_key_encryption.py tests/test_p8_observability_docs.py -q`

Expected: FAIL before implementation.

### Task 2: Implement observability stack compose + configs (`P8-004`)

**Files:**
- Modify: `docker-compose.yml`
- Create: `config/observability/prometheus.yml`
- Create: `config/observability/loki-config.yml`
- Create: `config/observability/tempo.yml`
- Create: `config/observability/alertmanager.yml`
- Create: `config/observability/grafana/datasources/datasources.yml`
- Create: `config/observability/grafana/dashboards/dashboards.yml`

### Task 3: Implement alert rules (`P8-005`)

**Files:**
- Create: `config/observability/alerts.yml`

### Task 4: Implement AES-256-GCM key encryption/store (`P8-006`)

**Files:**
- Modify: `pyproject.toml`
- Create: `services/shared/runtime/key_encryption.py`
- Create: `services/shared/runtime/exchange_credentials.py`
- Modify: `services/shared/runtime/__init__.py`

### Task 5: Docs and plan updates

**Files:**
- Modify: `README.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Create: `docs/observability_stack_deployment.md`
- Create: `docs/learning/2026-02-14-p8-004-p8-006-instincts.md`

### Task 6: Verification

Run:
- `uv run pytest tests/test_p8_observability_stack.py tests/test_p8_key_encryption.py tests/test_p8_observability_docs.py -q`
- `uv run pytest -q`
- `uv run ruff check .`
- `cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...`

Expected: PASS.

---

## Execution Log

- 2026-02-14: Plan created.
- 2026-02-14: Design recorded in `docs/plans/2026-02-14-p8-004-p8-006-observability-security-design.md`.
- 2026-02-14: Added failing tests for observability compose wiring, critical alert catalog coverage, encrypted key storage runtime behavior, and plan/docs status gates.
- 2026-02-14: Implemented observability stack config assets and compose services for Prometheus, Grafana, Loki, Tempo, and Alertmanager.
- 2026-02-14: Implemented critical alert rules and wired them into Prometheus rule loading with Alertmanager routing.
- 2026-02-14: Added AES-256-GCM key encryptor and encrypted exchange credential store runtime helpers backed by `exchanges` encrypted columns.
- 2026-02-14: Updated README, deployment documentation, and implementation plan status tracking for `P8-004..P8-006`.
