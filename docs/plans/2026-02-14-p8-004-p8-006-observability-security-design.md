# Phase 8 Observability Stack + Alert Rules + Key Encryption Design (P8-004/P8-005/P8-006)

## Scope

Complete the next Phase 8 tranche after observability baseline contracts:

- `P8-004`: Docker Compose observability stack wiring
- `P8-005`: Prometheus alert rules for critical events
- `P8-006`: AES-256-GCM encryption-at-rest runtime for persisted exchange keys

## Current Baseline

- Phase 8 baseline (`P8-001..P8-003`) exists with structured logging, in-process Prometheus exposition, and trace context helpers.
- No concrete Compose services for Prometheus/Grafana/Loki/Tempo/Alertmanager.
- No alert catalog file wired into Prometheus and Alertmanager config.
- Migration schema has encrypted exchange key columns (`api_key_encrypted`, `api_secret_encrypted`) but no runtime encryption codec/store implementation yet.

## Design

### 1) Compose Observability Stack (`P8-004`)

Add concrete observability services to `docker-compose.yml` under an `observability` profile:

- `prometheus`
- `grafana`
- `loki`
- `tempo`
- `alertmanager`

Add supporting config files under `config/observability/`:

- `prometheus.yml` (scrape + rule files + alertmanager target)
- `alerts.yml` (critical alert rules)
- `alertmanager.yml` (routing and receiver template)
- `loki-config.yml`
- `tempo.yml`
- `grafana/datasources/datasources.yml`
- `grafana/dashboards/dashboards.yml`

This keeps stack wiring deterministic and local-first while preserving current service behavior.

### 2) Alert Rule Catalog (`P8-005`)

Define first-pass critical rules in `config/observability/alerts.yml` aligned with ARD:

- exchange disconnect signal
- LLM quota breach signal
- drawdown/daily-loss risk breach signal
- elevated order failures
- data integrity resync events

Rules are based on metric names already present or planned and initially include pragmatic thresholds for local/prod tuning.

### 3) Exchange Key Encryption at Rest (`P8-006`)

Implement concrete runtime encryption and storage helpers:

- `services/shared/runtime/key_encryption.py`
  - AES-256-GCM codec using `ENCRYPTION_KEY_BASE64`
  - versioned encrypted payload format
  - explicit validation errors for malformed key/ciphertext
- `services/shared/runtime/exchange_credentials.py`
  - sqlite-backed encrypted credential store for `exchanges` table fields
  - upsert/load methods returning decrypted credentials

Security properties:

- never persist plaintext API key/secret
- nonce-per-encryption randomness
- authenticated decryption (GCM tag)
- context/AAD to bind ciphertext usage intent

## Testing Strategy

- Unit tests for encryption codec round-trip, invalid key length, and tamper detection.
- Store tests asserting DB never contains plaintext values and decrypts correctly.
- Compose/config tests for observability services + config paths + alert file wiring.
- Alert rule tests for required alert names and logical expression presence.

## Risks and Mitigations

- Risk: introducing cryptography dependency can destabilize local setup.
  - Mitigation: keep dependency minimal and explicitly documented in `pyproject.toml`.
- Risk: alert metric names diverge from runtime metrics.
  - Mitigation: keep rule names stable and document metric assumptions for upcoming `P8-007`/`P9` tuning.
- Risk: stack configs become stale versus compose wiring.
  - Mitigation: add file-presence and wiring tests to enforce drift detection.
