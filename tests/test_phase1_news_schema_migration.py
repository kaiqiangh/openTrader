from pathlib import Path


def test_news_schema_migration_exists() -> None:
    assert Path("migrations/versions/20260214_0005_news_schema.py").exists()


def test_news_schema_migration_has_required_tables() -> None:
    content = Path("migrations/versions/20260214_0005_news_schema.py").read_text(
        encoding="utf-8"
    )
    assert "news_items" in content
    assert "news_tags" in content
    assert "news_summaries" in content
    assert "decision_news_links" in content


def test_news_schema_migration_has_constraints_and_indexes() -> None:
    content = Path("migrations/versions/20260214_0005_news_schema.py").read_text(
        encoding="utf-8"
    )
    assert "uq_news_items_source_source_item_id" in content
    assert "idx_news_items_published_at" in content
    assert "idx_news_tags_symbol_topic" in content
    assert "idx_news_summaries_symbol_scope_window" in content
    assert "pk_decision_news_links" in content
    assert 'sa.ForeignKey("decision_traces.decision_id")' in content
    assert 'sa.ForeignKey("news_summaries.summary_id")' in content
    assert 'sa.ForeignKey("news_items.news_id")' in content


def test_readme_mentions_news_schema_migration() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "20260214_0005_news_schema.py" in content
