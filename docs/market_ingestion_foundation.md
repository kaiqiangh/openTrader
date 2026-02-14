# Market Ingestion Foundation (P2-001..P2-006)

This document defines the first production-facing ingestion and integrity components for Phase 2:

- `services/market_ingestion/exchange_adapter.py` (`P2-001`)
- `services/market_ingestion/connection_resilience.py` (`P2-002`)
- `services/market_ingestion/order_book_sync.py` (`P2-003`)
- `services/market_ingestion/gap_detection.py` (`P2-004`)
- `services/market_ingestion/kline_validator.py` (`P2-005`)
- `services/market_ingestion/canonical_pipeline.py` (`P2-006`)

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

5. `gap_detection.py`
- Converts sequence windows into explicit actions: `accept`, `ignore_stale`, `resync`.
- Builds controlled resync request payloads with expected vs received sequence context.

6. `kline_validator.py`
- Validates k-line reconstruction integrity:
  - monotonic open times
  - fixed interval continuity
  - missing bar detection
  - high/low/open/close consistency.

7. `canonical_pipeline.py`
- Normalizes ingestion artifacts to canonical market payloads.
- Wraps payloads with shared message envelope contract fields.
- Publishes validated envelopes to routing key `market.canonical`.

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
- Gap detection policy:
  - If incoming start is above expected: action `resync`.
  - If incoming window is stale: action `ignore_stale`.
  - Otherwise: action `accept`.
- Canonical event contract:
  - Uses shared envelope fields (`trace_id`, `decision_id`, `mode`, `idempotency_key`, `event_type`, `emitted_at`, `payload`).
  - Envelope is validated before publish.

## Usage Flow

1. Initialize `CCXTIngestionAdapter(exchange, rest_client, ws_client)`.
2. Fetch initial snapshot with `bootstrap_snapshot(...)`.
3. Load snapshot into `OrderBookSyncEngine`.
4. For each `poll_delta(...)` result:
- Apply via `apply_delta(...)`.
- On `OrderBookSequenceGapError`, call `GapDetectionModule.evaluate(...)`.
- If action is `resync`, create a resync request and re-bootstrap snapshot.
5. Run `KlineReconstructionValidator` on reconstructed bar windows.
6. Publish normalized canonical events with `CanonicalNormalizationPipeline`.
7. Use `ConnectionResilienceManager` to drive reconnect delays when feeds go stale.
