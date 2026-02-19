from pathlib import Path
import re


def test_phase3_alert_catalog_includes_slo_rules() -> None:
    alerts = Path("config/observability/alerts.yml").read_text(encoding="utf-8")
    for alert_name in (
        "MarketIngestionLagP95High",
        "WebsocketStreamStale",
        "LLMRequestLatencyP95High",
        "LLMCostHourlySpike",
        "ExecutionLatencyP95High",
        "RiskBlocksElevated",
    ):
        assert re.search(rf"alert:\s*{alert_name}", alerts)
    assert "open_trader_market_ingestion_lag_ms_bucket" in alerts
    assert "open_trader_llm_request_latency_seconds_bucket" in alerts
    assert "open_trader_execution_dispatch_latency_seconds_bucket" in alerts


def test_phase3_grafana_dashboard_mentions_p95_slo_panels() -> None:
    dashboard = Path("config/observability/grafana/dashboard-definitions/open-trader-overview.json")
    content = dashboard.read_text(encoding="utf-8")
    assert "Market Ingestion Lag p95 (ms)" in content
    assert "LLM Request Latency p95 (s)" in content
    assert "Execution Dispatch Latency p95 (s)" in content
    assert "open_trader_market_ingestion_lag_ms_bucket" in content
    assert "open_trader_llm_request_latency_seconds_bucket" in content
    assert "open_trader_execution_dispatch_latency_seconds_bucket" in content
