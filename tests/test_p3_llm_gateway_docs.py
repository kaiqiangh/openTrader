from pathlib import Path


def test_llm_gateway_baseline_doc_exists() -> None:
    assert Path("docs/llm_gateway_baseline.md").exists()


def test_llm_gateway_learning_doc_exists() -> None:
    assert Path("docs/learning/2026-02-14-p3-llm-gateway-instincts.md").exists()


def test_llm_gateway_baseline_mentions_gateway_modules() -> None:
    content = Path("docs/llm_gateway_baseline.md").read_text(encoding="utf-8")
    assert "services/llm_gateway/contracts.py" in content
    assert "services/llm_gateway/gateway.py" in content


def test_readme_mentions_llm_gateway_modules() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "services/llm_gateway/contracts.py" in content
    assert "services/llm_gateway/gateway.py" in content
    assert "docs/llm_gateway_baseline.md" in content
