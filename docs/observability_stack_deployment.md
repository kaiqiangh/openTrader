# Observability Stack Deployment Notes

## Scope

Defines Docker Compose deployment wiring for the Phase 8 observability stack (`P8-004`) and alert rules (`P8-005`).

## Services

- `prometheus` (port `9090`)
- `grafana` (port `3000`)
- `loki` (port `3100`)
- `tempo` (port `3200`)
- `alertmanager` (port `9093`)

All services run under compose profile `observability`.

## Startup

1. Start stack:
   - `docker compose --profile observability up -d prometheus grafana loki tempo alertmanager`
2. Verify:
   - `docker compose ps`
   - `docker compose exec prometheus wget -qO- http://localhost:9090/-/ready || true`
   - `curl -s http://127.0.0.1:3000/api/health`

## Configuration Files

- Prometheus: `config/observability/prometheus.yml`
- Alert rules: `config/observability/alerts.yml`
- Alertmanager: `config/observability/alertmanager.yml`
- Loki: `config/observability/loki-config.yml`
- Tempo: `config/observability/tempo.yml`
- Grafana datasources: `config/observability/grafana/datasources/datasources.yml`
- Grafana dashboards: `config/observability/grafana/dashboards/dashboards.yml`

## Alert Catalog

Critical and warning rule set includes:

- `ExchangeConnectivityIssue`
- `LLMQuotaBreach`
- `RiskDrawdownBreach`
- `ElevatedOrderFailures`
- `IntegrityResyncEvents`

## Security Notes

- `GRAFANA_ADMIN_USER` and `GRAFANA_ADMIN_PASSWORD` are sourced from `.env`.
- Network isolation baseline:
  - public-facing network: `public`
  - internal-only network: `internal` (`internal: true`)
  - only Grafana is exposed to host by default in this phase.
- Exchange API key encryption at rest is handled separately by `P8-006` runtime helpers in `services/shared/runtime/key_encryption.py` and `services/shared/runtime/exchange_credentials.py`.
