from pathlib import Path


def test_mock_realtime_workflow_script_exists_and_covers_expected_flow() -> None:
    script = Path("scripts/mock_realtime_workflow_test.py")
    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "market.canonical.orderbook_delta" in content
    assert "LLMGateway" in content
    assert "LiteLLMHTTPProviderClient" in content
    assert "orderbook_snapshots" in content
    assert "klines" in content
    assert "news_summaries" in content
    assert "llm_calls" in content
    assert "decision_traces" in content
    assert "agent_runs" in content
    assert "agent_messages" in content
    assert "orders" in content
    assert "fills" in content
    assert "portfolio_snapshots" in content
    assert "decision_news_links" in content
    assert "--seed" in content
    assert "--symbol" in content
    assert "--interval" in content
    assert "--lookback-minutes" in content
    assert "--market-exchanges" in content


def test_makefile_exposes_mock_workflow_target() -> None:
    content = Path("Makefile").read_text(encoding="utf-8")
    assert "mock-workflow" in content
    assert "uv run python scripts/mock_realtime_workflow_test.py" in content
