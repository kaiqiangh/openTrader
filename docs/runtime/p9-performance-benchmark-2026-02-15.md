# Phase 9 Performance Benchmark Evidence (2026-02-15)

## Scope

Validation evidence for `P9-005`:

- Dispatch latency sampling for simulation execution worker.
- Queue throughput sampling for broker publish/consume path.
- Ingestion lag sampling for canonical market envelope publish.

## Commands Executed

1. `uv run pytest tests/test_p9_performance_benchmarks.py -q`
2. `uv run python - <<'PY' ...` (benchmark snapshot helper; same harness configuration as test suite)

## Benchmark Snapshot

- Dispatch latency (`SimulationExecutionWorker.run_once`, 180 samples):
  - `p50`: `0.027ms`
  - `p95`: `0.044ms`
  - `max`: `0.559ms`
- Queue throughput (`InMemoryTopicBroker` publish+consume, 1200 samples):
  - `860137.98 msg/s`
- Ingestion lag (`MarketIngestionRuntimeWorker` canonical envelope lag, 60 samples):
  - `p50`: `0ms`
  - `p95`: `0ms`
  - `max`: `0ms`

## Outcome

- `tests/test_p9_performance_benchmarks.py`: PASS
- All benchmark checks satisfy configured Phase 9 validation thresholds.
- `P9-005` is validated and marked complete in `docs/IMPLEMENTATION_PLAN.md`.
