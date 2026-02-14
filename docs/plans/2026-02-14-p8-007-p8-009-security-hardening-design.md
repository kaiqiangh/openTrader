# Phase 8 Network Isolation + Security Suite + Runbooks Design (P8-007/P8-008/P8-009)

## Scope

Complete the remaining Phase 8 hardening tasks:

- `P8-007`: network isolation hardening in Docker Compose
- `P8-008`: security validation test suite
- `P8-009`: operational incident runbooks

## Current Baseline

- Compose includes observability services and one `internal` network, but no explicit public/internal split.
- Security-sensitive key encryption runtime exists (`AES-256-GCM`) and env validation enforces key shape.
- RBAC/auth tests exist but no dedicated consolidated security suite artifact for Phase 8 acceptance.
- No runbook set covering exchange outage, quota breach, and risk incidents.

## Design

### 1) Compose Network Isolation (`P8-007`)

Refactor `docker-compose.yml` network topology:

- define two networks:
  - `public`: for externally reachable UI/control surfaces
  - `internal` with `internal: true`: for broker/data/runtime service mesh
- remove host port exposures for internal-only services (postgres/redis/rabbitmq/loki/tempo/alertmanager/prometheus)
- keep only Grafana exposed on localhost as operator-facing surface in this phase
- attach services explicitly:
  - internal-only: data stores, broker, worker, trace/log backends
  - mixed (public + internal): grafana

### 2) Security Validation Suite (`P8-008`)

Add dedicated security regression tests:

- compose isolation assertions (internal services not exposed)
- JWT issuer/audience mismatch rejection tests
- encryption store non-plaintext persistence and decrypt round-trip assertions
- run tests as explicit security suite target

### 3) Incident Runbooks (`P8-009`)

Add structured operational runbooks under `docs/runbooks/`:

- exchange outage incident
- LLM quota breach incident
- risk breach incident

Each runbook includes:

- detection signals
- immediate containment actions
- communication/escalation path
- recovery validation checklist
- post-incident actions

## Validation

- targeted security/network/runbook tests pass
- full Python and Go suites remain green
- `IMPLEMENTATION_PLAN.md` marks `P8-007..P8-009` as `DONE`

## Risks and Mitigations

- Risk: removing host ports reduces local debugging convenience.
  - Mitigation: runbook includes inspection commands via `docker compose exec/logs`.
- Risk: security checks overlap existing tests and become noisy.
  - Mitigation: keep security suite scoped to acceptance-critical assertions only.
