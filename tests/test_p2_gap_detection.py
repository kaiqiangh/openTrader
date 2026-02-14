from services.market_ingestion.gap_detection import GapDetectionModule


def test_detect_gap_when_sequence_start_skips_expected() -> None:
    detector = GapDetectionModule()
    result = detector.evaluate(current_sequence=100, incoming_start=105, incoming_end=105)

    assert result.has_gap is True
    assert result.expected_sequence == 101
    assert result.received_sequence_start == 105
    assert result.gap_size == 4
    assert result.action == "resync"


def test_no_gap_for_contiguous_delta() -> None:
    detector = GapDetectionModule()
    result = detector.evaluate(current_sequence=100, incoming_start=101, incoming_end=103)

    assert result.has_gap is False
    assert result.action == "accept"


def test_stale_delta_is_ignored_not_resync() -> None:
    detector = GapDetectionModule()
    result = detector.evaluate(current_sequence=100, incoming_start=90, incoming_end=100)

    assert result.has_gap is False
    assert result.action == "ignore_stale"


def test_build_resync_request_contains_sequence_context() -> None:
    detector = GapDetectionModule()
    result = detector.evaluate(current_sequence=100, incoming_start=108, incoming_end=110)
    request = detector.build_resync_request(
        exchange="binance",
        symbol="BTC/USDT",
        result=result,
        reason="sequence_gap",
    )

    assert request["exchange"] == "binance"
    assert request["symbol"] == "BTC/USDT"
    assert request["reason"] == "sequence_gap"
    assert request["expected_sequence"] == 101
    assert request["received_sequence_start"] == 108
