from services.market_ingestion.kline_validator import KlineBar, KlineReconstructionValidator


def test_validator_accepts_contiguous_monotonic_klines() -> None:
    bars = [
        KlineBar(1700000000000, 10.0, 11.0, 9.5, 10.5, 100.0),
        KlineBar(1700000060000, 10.5, 12.0, 10.0, 11.8, 120.0),
        KlineBar(1700000120000, 11.8, 12.2, 11.0, 11.2, 90.0),
    ]
    validator = KlineReconstructionValidator(interval_ms=60_000)
    result = validator.validate(bars)

    assert result.is_valid is True
    assert result.missing_open_times == ()
    assert result.errors == ()


def test_validator_detects_missing_interval() -> None:
    bars = [
        KlineBar(1700000000000, 10.0, 11.0, 9.5, 10.5, 100.0),
        KlineBar(1700000120000, 10.5, 12.0, 10.0, 11.8, 120.0),
    ]
    validator = KlineReconstructionValidator(interval_ms=60_000)
    result = validator.validate(bars)

    assert result.is_valid is False
    assert 1700000060000 in result.missing_open_times


def test_validator_detects_non_monotonic_order() -> None:
    bars = [
        KlineBar(1700000120000, 10.0, 11.0, 9.5, 10.5, 100.0),
        KlineBar(1700000060000, 10.5, 12.0, 10.0, 11.8, 120.0),
    ]
    validator = KlineReconstructionValidator(interval_ms=60_000)
    result = validator.validate(bars)

    assert result.is_valid is False
    assert any("monotonic" in error for error in result.errors)


def test_validator_detects_price_consistency_errors() -> None:
    bars = [
        KlineBar(1700000000000, 10.0, 9.0, 11.0, 10.5, 100.0),
    ]
    validator = KlineReconstructionValidator(interval_ms=60_000)
    result = validator.validate(bars)

    assert result.is_valid is False
    assert any("high/low" in error for error in result.errors)
