from pathlib import Path


def test_verify_klines_script_exists_and_targets_expected_tables() -> None:
    script = Path("scripts/verify_klines_persistence.py")
    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "klines" in content
    assert "--symbol" in content
    assert "--interval" in content
    assert "--exchanges" in content
    assert "--minutes" in content


def test_verify_orderbook_script_exists_and_targets_expected_tables() -> None:
    script = Path("scripts/verify_orderbook_snapshots.py")
    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "orderbook_snapshots" in content
    assert "--symbol" in content
    assert "--exchanges" in content
    assert "--minutes" in content
    assert "--expected-interval-seconds" in content
