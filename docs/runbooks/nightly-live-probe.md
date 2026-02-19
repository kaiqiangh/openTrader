# Nightly Live Probe Runbook

## Detection Signals

- Nightly workflow `.github/workflows/nightly-live-probe.yml` fails.
- Missing or stale `artifacts/live_runtime_probe/latest.json`.
- Alerts from live probe pipeline indicate exchange/LLM/runtime dependency failures.

## Immediate Actions

1. Open the failed workflow run and inspect failing step.
2. Check whether failure is infra (compose/services), exchange reachability, or LLM provider.
3. Re-run probe manually in workspace:
   - `uv run python scripts/live_runtime_probe.py --skip-compose`
4. If outage is external, mark incident as dependency-originated and keep PR CI green.

## Escalation

- Escalate to platform owner for repeat nightly failures (2 consecutive nights).
- Escalate to LLM provider owner for authentication/quota failures.
- Escalate to exchange connectivity owner for market data acquisition failures.

## Recovery Validation

1. Confirm nightly probe rerun succeeds.
2. Confirm artifact output includes `overall_status: ok`.
3. Confirm probe generated fresh timestamp and no stale warning.

## Post-Incident Actions

1. Record root cause and owner in incident log.
2. Add/adjust gating checks in `scripts/live_runtime_probe.py` if blind spots were found.
3. Update workflow secrets documentation when credentials were the cause.
