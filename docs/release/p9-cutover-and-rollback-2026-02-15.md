# P9 Cutover and Rollback Runbook (2026-02-15)

## Cutover Steps

1. Confirm preflight checklist completion:
   - `docs/release/p9-release-checklist-2026-02-15.md`
2. Snapshot current runtime state:
   - `docker compose ps`
   - `docker compose logs --tail=100 notification_worker`
3. Apply migrations:
   - `make migrate-up`
4. Start/refresh services:
   - `docker compose up -d`
5. Validate health endpoints and core runtime:
   - API readiness/liveness
   - `/metrics` scrape
   - notification worker `--validate-only`
6. Execute smoke validation:
   - `make smoke`
7. Declare cutover completion in operations channel and start hypercare window.

## Rollback Triggers

- Critical runtime startup failure unresolved within agreed rollback timeout.
- Persistent order/position/risk inconsistency in Phase 9 acceptance checks.
- Critical security control failure (auth bypass, secret leak, encryption failure).
- Sustained alert storm indicating unrecoverable degraded state.

## Rollback Procedure

1. Announce rollback in operations channel.
2. Stop newly rolled services:
   - `docker compose down`
3. Restore previous known-good runtime/deployment state (tagged artifact or prior compose revision).
4. If migration rollback is required:
   - run controlled downgrade command and verify schema compatibility.
5. Bring previous stable services up:
   - `docker compose up -d`
6. Re-run minimal validation:
   - health endpoints
   - `make smoke` (or reduced smoke set if time-critical)
7. Record incident timeline and assign postmortem owner.

## First-Hour Hypercare Checks

- Monitor API error rate, latency, and authentication failures.
- Monitor notification delivery failures/retry spikes.
- Monitor replay and integrity validation alerts.
- Monitor risk/circuit-breaker/kill-switch events for anomaly spikes.
- Confirm no unexpected queue backlogs.
