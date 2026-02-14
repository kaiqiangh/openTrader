# Exchange Outage Runbook

## Scope

Incident response workflow for exchange connectivity failures (websocket disconnects, REST unavailability, or repeated reconnect failures).

## Detection Signals

- Alert fired: `ExchangeConnectivityIssue`
- Notification events containing `system.exchange.connectivity_issue`
- Elevated reconnect/resync counters in ingestion telemetry
- Stalled `market.canonical.*` event flow

## Immediate Actions

1. Confirm scope:
   - `docker compose logs --tail=200 market_ingestion || true`
   - `docker compose logs --tail=200 notification_worker || true`
2. Switch execution mode to protective state (if trading is active):
   - Set mode to `MOCK` via control API.
3. Enable risk protection controls:
   - Trip circuit breaker and, if needed, enable kill switch.
4. Verify broker/data health:
   - `docker compose ps rabbitmq redis postgres_timescaledb`

## Escalation

1. Notify on-call operator and incident channel with:
   - impacted exchange(s)
   - first detection timestamp
   - current execution mode and risk control state
2. Escalate to platform owner if outage exceeds 10 minutes or affects multi-exchange routing.

## Recovery Validation

1. Confirm exchange connectivity restoration:
   - reconnect/resync counters stabilize
   - canonical market events resume with fresh timestamps
2. Validate downstream pipeline:
   - orchestrator receives market events
   - notification stream no longer emits connectivity critical alerts
3. Perform controlled return:
   - disable kill switch/circuit breaker only after stability window passes.

## Post-Incident Actions

1. Record timeline, root cause hypothesis, and mitigations in incident report.
2. Capture permanent fixes (backoff tuning, adapter patch, alert threshold changes).
3. Update this runbook if response steps were missing or unclear.
