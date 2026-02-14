# Market Ingestion Foundation (P2-001/P2-002/P2-003)

This document defines the first production-facing ingestion components for Phase 2:

- `services/market_ingestion/exchange_adapter.py` (`P2-001`)
- `services/market_ingestion/connection_resilience.py` (`P2-002`)
- `services/market_ingestion/order_book_sync.py` (`P2-003`)

## Component Boundaries

1. `contracts.py`
- Canonical in-process types: `OrderBookSnapshot`, `OrderBookDelta`, `OrderBookLevel`.

2. `exchange_adapter.py`
- Normalizes CCXT-like REST snapshot and WebSocket update payloads.
- Exposes:
  - `bootstrap_snapshot(symbol, limit)` for snapshot bootstrap.
  - `poll_delta(symbol, limit)` for incremental updates.

3. `connection_resilience.py`
- Tracks heartbeat freshness and reconnect attempt state.
- Provides capped exponential backoff with jitter.

4. `order_book_sync.py`
- Applies snapshot + delta updates deterministically.
- Detects sequence gaps and rejects stale deltas.

## Internal Contract Notes

- Adapter input contract:
  - Snapshot payload requires `bids` and `asks` arrays.
  - Delta payload requires `bids` and `asks` arrays.
  - Sequence sources:
    - Delta: `U/u` (preferred), then `sequence_start/sequence_end`, then `nonce`.
    - Snapshot: `nonce` or `sequence`.
- Sync engine sequence policy:
  - Expected sequence is `current + 1`.
  - `delta.sequence_end < expected` => stale delta ignored.
  - `delta.sequence_start > expected` => `OrderBookSequenceGapError`.

## Usage Flow

1. Initialize `CCXTIngestionAdapter(exchange, rest_client, ws_client)`.
2. Fetch initial snapshot with `bootstrap_snapshot(...)`.
3. Load snapshot into `OrderBookSyncEngine`.
4. For each `poll_delta(...)` result:
- Apply via `apply_delta(...)`.
- On `OrderBookSequenceGapError`, re-bootstrap snapshot and continue.
5. Use `ConnectionResilienceManager` to drive reconnect delays when feeds go stale.
