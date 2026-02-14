from pathlib import Path


def test_agent_runtime_baseline_doc_exists() -> None:
    assert Path("docs/agent_runtime_baseline.md").exists()


def test_agent_runtime_instinct_doc_exists() -> None:
    assert Path("docs/learning/2026-02-14-p3-agent-runtime-instincts.md").exists()


def test_execution_decision_instinct_doc_exists() -> None:
    assert Path("docs/learning/2026-02-14-p3-execution-decision-instincts.md").exists()


def test_market_context_instinct_doc_exists() -> None:
    assert Path("docs/learning/2026-02-14-p3-market-context-instincts.md").exists()


def test_agent_runtime_doc_mentions_p3_modules() -> None:
    content = Path("docs/agent_runtime_baseline.md").read_text(encoding="utf-8")
    assert "orchestrator.py" in content
    assert "planner_agent.py" in content
    assert "risk_agent.py" in content
    assert "execution_decision_agent.py" in content
    assert "market_context_agent.py" in content


def test_readme_mentions_p3_agent_runtime_modules() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "services/agent_orchestrator/orchestrator.py" in content
    assert "services/agent_orchestrator/planner_agent.py" in content
    assert "services/agent_orchestrator/risk_agent.py" in content
    assert "services/agent_orchestrator/execution_decision_agent.py" in content
    assert "services/agent_orchestrator/market_context_agent.py" in content
    assert "docs/agent_runtime_baseline.md" in content
