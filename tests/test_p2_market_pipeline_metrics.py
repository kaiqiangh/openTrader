from services.market_ingestion.pipeline_metrics import MarketPipelineMetrics


def test_metrics_snapshot_exposes_lag_rate_and_reconnects() -> None:
    metrics = MarketPipelineMetrics()
    metrics.record_delta_processed(lag_ms=80.0, now_seconds=100.0)
    metrics.record_delta_processed(lag_ms=120.0, now_seconds=101.0)
    metrics.record_reconnect(now_seconds=101.1)
    metrics.record_resync_request(now_seconds=101.2)

    snapshot = metrics.snapshot(now_seconds=130.0)

    assert snapshot["counters"]["deltas_processed_total"] == 2
    assert snapshot["counters"]["reconnects_total"] == 1
    assert snapshot["counters"]["resync_requests_total"] == 1
    assert snapshot["lag_ms"]["latest"] == 120.0
    assert snapshot["lag_ms"]["max"] == 120.0
    assert snapshot["rates"]["events_per_second_60s"] > 0


def test_events_rate_window_excludes_old_events() -> None:
    metrics = MarketPipelineMetrics()
    metrics.record_delta_processed(lag_ms=50.0, now_seconds=10.0)
    metrics.record_delta_processed(lag_ms=60.0, now_seconds=20.0)
    metrics.record_delta_processed(lag_ms=70.0, now_seconds=100.0)

    rate = metrics.events_per_second(window_seconds=30.0, now_seconds=100.0)

    assert rate == 1 / 30.0


def test_metrics_handles_empty_state() -> None:
    metrics = MarketPipelineMetrics()
    snapshot = metrics.snapshot(now_seconds=200.0)

    assert snapshot["counters"]["deltas_processed_total"] == 0
    assert snapshot["lag_ms"]["latest"] is None
    assert snapshot["rates"]["events_per_second_60s"] == 0.0
