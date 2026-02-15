from pathlib import Path


def test_mock_realtime_workflow_script_exists_and_covers_expected_flow() -> None:
    script = Path("scripts/mock_realtime_workflow_test.py")
    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "market.canonical.orderbook_delta" in content
    assert "execution.intent.mock" in content
    assert "oms.order." in content
    assert "notify." in content
    assert "news_items" in content
    assert "LiteLLMHTTPProviderClient" in content
    assert "BinanceHTTPOrderBookClient" in content
    assert "BitgetHTTPOrderBookClient" in content
    assert "_fetch_real_news_context" in content


def test_makefile_exposes_mock_workflow_target() -> None:
    content = Path("Makefile").read_text(encoding="utf-8")
    assert "mock-workflow" in content
    assert "uv run python scripts/mock_realtime_workflow_test.py" in content
