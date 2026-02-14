from pathlib import Path


def test_llm_governance_migration_exists() -> None:
    assert Path("migrations/versions/20260214_0004_llm_governance_schema.py").exists()


def test_llm_governance_tables_present() -> None:
    content = Path("migrations/versions/20260214_0004_llm_governance_schema.py").read_text(
        encoding="utf-8"
    )
    assert "llm_calls" in content
    assert "llm_usage_daily" in content
    assert "llm_usage_monthly" in content
    assert "llm_quota_limits" in content


def test_readme_mentions_llm_governance_migration() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "20260214_0004_llm_governance_schema.py" in content
