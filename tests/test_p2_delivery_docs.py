from pathlib import Path


def test_delivery_instinct_doc_exists() -> None:
    assert Path("docs/learning/2026-02-14-p2-delivery-instincts.md").exists()


def test_market_ingestion_foundation_mentions_delivery_modules() -> None:
    content = Path("docs/market_ingestion_foundation.md").read_text(encoding="utf-8")
    assert "persistence_writers.py" in content
    assert "pipeline_metrics.py" in content
    assert "integration_harness.py" in content


def test_readme_mentions_p2_delivery_modules() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "services/market_ingestion/persistence_writers.py" in content
    assert "services/market_ingestion/pipeline_metrics.py" in content
    assert "services/market_ingestion/integration_harness.py" in content
