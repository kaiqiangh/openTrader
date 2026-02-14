# AGENT.md

## Responsibility

Defines versioned observability stack configuration for local/compose deployment.

## Architectural Boundaries

- Contains configuration only (Prometheus/Grafana/Loki/Tempo/Alertmanager).
- Must not include service business logic.

## Coding Conventions

- Keep configs deterministic and environment-agnostic where possible.
- Prefer explicit file paths and stable scrape/alert labels.

## Dependency Rules

- Compose services may mount these configs read-only.
- Runtime services must not mutate these files.

## Extension Rules

- New scrape jobs require documented metrics path and target rationale.
- New alert rules require severity and runbook-ready annotations.

## Integration Contracts

- `prometheus.yml` references `alerts.yml` and `alertmanager`.
- Grafana datasource provisioning must align with compose hostnames.

## Testing Expectations

- Tests should verify file presence, compose wiring, and critical alert rule coverage.

## Operational Notes

- Threshold tuning is environment-specific and should be iterated with live telemetry after deployment.
