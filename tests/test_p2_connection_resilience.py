from services.market_ingestion.connection_resilience import BackoffConfig, ConnectionResilienceManager


def test_is_stale_based_on_last_heartbeat() -> None:
    manager = ConnectionResilienceManager(
        config=BackoffConfig(stale_after_seconds=10.0),
        random_fn=lambda: 0.5,
    )
    manager.mark_heartbeat(now_seconds=100.0)

    assert manager.is_stale(now_seconds=108.0) is False
    assert manager.is_stale(now_seconds=111.0) is True


def test_next_backoff_grows_with_attempts_and_cap() -> None:
    manager = ConnectionResilienceManager(
        config=BackoffConfig(
            base_delay_seconds=1.0,
            max_delay_seconds=5.0,
            backoff_multiplier=2.0,
            jitter_ratio=0.0,
        ),
        random_fn=lambda: 0.5,
    )

    assert manager.next_backoff_seconds(attempt=1) == 1.0
    assert manager.next_backoff_seconds(attempt=2) == 2.0
    assert manager.next_backoff_seconds(attempt=3) == 4.0
    assert manager.next_backoff_seconds(attempt=4) == 5.0


def test_disconnect_attempts_reset_after_successful_reconnect() -> None:
    manager = ConnectionResilienceManager(
        config=BackoffConfig(base_delay_seconds=1.0, jitter_ratio=0.0),
        random_fn=lambda: 0.5,
    )

    first_delay = manager.record_disconnect(now_seconds=10.0)
    second_delay = manager.record_disconnect(now_seconds=11.0)
    assert second_delay > first_delay

    manager.record_reconnect_success(now_seconds=12.0)
    reset_delay = manager.record_disconnect(now_seconds=13.0)
    assert reset_delay == first_delay
