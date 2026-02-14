from pathlib import Path


def test_news_connector_framework_files_exist() -> None:
    assert Path("services/news_ingestion/source_connectors.py").exists()
    assert Path("services/news_ingestion/__init__.py").exists()


def test_readme_mentions_p6_source_connector_framework() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "services/news_ingestion/source_connectors.py" in content


def test_implementation_plan_marks_p6_001_done() -> None:
    content = Path("docs/IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")
    assert "| P6-001 |" in content and "| DONE |" in content
