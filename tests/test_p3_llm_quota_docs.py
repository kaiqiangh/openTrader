from pathlib import Path


def test_llm_quota_instinct_doc_exists() -> None:
    assert Path("docs/learning/2026-02-14-p3-llm-quota-instincts.md").exists()


def test_llm_gateway_baseline_mentions_quota_module() -> None:
    content = Path("docs/llm_gateway_baseline.md").read_text(encoding="utf-8")
    assert "services/llm_gateway/quota.py" in content
    assert "QuotaLimits" in content
    assert "LLMQuotaStore" in content


def test_readme_mentions_llm_quota_module() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "services/llm_gateway/quota.py" in content
    assert "docs/learning/2026-02-14-p3-llm-quota-instincts.md" in content
