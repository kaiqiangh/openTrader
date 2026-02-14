from pathlib import Path


def test_news_connector_framework_files_exist() -> None:
    assert Path("services/news_ingestion/source_connectors.py").exists()
    assert Path("services/news_ingestion/__init__.py").exists()
    assert Path("services/news_ingestion/ingestion_service.py").exists()
    assert Path("services/news_ingestion/tagging_relevance.py").exists()
    assert Path("services/news_ingestion/quality_metrics.py").exists()
    assert Path("services/news_summarizer/summarizer_service.py").exists()
    assert Path("services/news_summarizer/context_injection_bridge.py").exists()
    assert Path("services/news_summarizer/resilience.py").exists()
    assert Path("services/news_summarizer/__init__.py").exists()


def test_readme_mentions_p6_source_connector_framework() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "services/news_ingestion/source_connectors.py" in content
    assert "services/news_ingestion/ingestion_service.py" in content
    assert "services/news_ingestion/tagging_relevance.py" in content
    assert "services/news_ingestion/quality_metrics.py" in content
    assert "services/news_summarizer/summarizer_service.py" in content
    assert "services/news_summarizer/context_injection_bridge.py" in content
    assert "services/news_summarizer/resilience.py" in content


def test_implementation_plan_marks_p6_001_to_p6_007_done() -> None:
    content = Path("docs/IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")
    assert "| P6-001 |" in content and "| DONE |" in content
    assert "| P6-002 |" in content and "| DONE |" in content
    assert "| P6-003 |" in content and "| DONE |" in content
    assert "| P6-004 |" in content and "| DONE |" in content
    assert "| P6-005 |" in content and "| DONE |" in content
    assert "| P6-006 |" in content and "| DONE |" in content
    assert "| P6-007 |" in content and "| DONE |" in content
