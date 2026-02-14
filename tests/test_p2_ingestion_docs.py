from pathlib import Path


def test_market_ingestion_foundation_doc_exists() -> None:
    assert Path("docs/market_ingestion_foundation.md").exists()


def test_learning_instinct_doc_exists() -> None:
    assert Path("docs/learning/2026-02-14-p2-ingestion-instincts.md").exists()


def test_readme_mentions_market_ingestion_foundation_docs() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "docs/market_ingestion_foundation.md" in content
