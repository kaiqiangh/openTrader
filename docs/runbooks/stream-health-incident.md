# Stream Health Incident Runbook

## Detection Signals

- `WebsocketStreamStale` alert firing from `config/observability/alerts.yml`.
- Elevated `open_trader_market_stream_stale_cutovers_total`.
- Elevated `open_trader_integrity_resync_requests_total`.
- Runtime logs show repeated websocket fallback/resync for the same symbol/exchange.

## Immediate Actions

1. Confirm whether impact is exchange-specific (`binance` vs `bitget`) or broad.
2. Verify runtime worker mode and fetch mode:
   - `MARKET_DATA_FETCH_MODE`
   - `MARKET_USE_CCXT_PRO`
3. Confirm REST fallback is active and publishing canonical market events.
4. If orderbook data quality is degraded, reduce strategy blast radius:
   - switch API mode to `MOCK`
   - trip circuit breaker if needed.

## Escalation

- Page trading ops primary if stale cutover lasts > 10 minutes.
- Escalate to platform owner if both exchanges are stale simultaneously.
- Escalate to exchange support channels when public status pages are green but stream quality is degraded.

## Recovery Validation

1. Verify websocket heartbeat recovery in worker logs.
2. Confirm stale-cutover counter stops increasing.
3. Confirm resync counter returns to normal baseline.
4. Validate `market.canonical.orderbook_delta` continues with monotonic sequence progression.
5. Run:
   - `uv run pytest -q tests/test_phase3_websocket_integrity_runtime.py`

## Post-Incident Actions

1. Record incident timeline and affected symbols/exchanges.
2. Capture before/after metric snapshots for lag and cutover counters.
3. Update stale thresholds/backoff configuration if the incident pattern repeats.
4. Add new regression test fixtures if a novel failure mode was observed.
