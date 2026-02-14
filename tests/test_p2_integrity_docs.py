from pathlib import Path


def test_integrity_instinct_doc_exists() -> None:
    assert Path("docs/learning/2026-02-14-p2-integrity-instincts.md").exists()


def test_market_ingestion_foundation_mentions_gap_and_kline_and_canonical() -> None:
    content = Path("docs/market_ingestion_foundation.md").read_text(encoding="utf-8")
    assert "gap_detection.py" in content
    assert "kline_validator.py" in content
    assert "canonical_pipeline.py" in content


def test_readme_mentions_p2_integrity_modules() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "services/market_ingestion/gap_detection.py" in content
    assert "services/market_ingestion/kline_validator.py" in content
    assert "services/market_ingestion/canonical_pipeline.py" in content
