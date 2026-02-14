from pathlib import Path
import re


def test_compose_includes_observability_stack_services() -> None:
    content = Path("docker-compose.yml").read_text(encoding="utf-8")
    for service_name in ("prometheus", "grafana", "loki", "tempo", "alertmanager"):
        assert f"{service_name}:" in content
    assert "profiles:" not in content


def test_observability_config_files_exist_and_are_wired() -> None:
    required_paths = [
        "config/observability/prometheus.yml",
        "config/observability/alerts.yml",
        "config/observability/alertmanager.yml",
        "config/observability/loki-config.yml",
        "config/observability/tempo.yml",
        "config/observability/grafana/datasources/datasources.yml",
        "config/observability/grafana/dashboards/dashboards.yml",
    ]
    for path in required_paths:
        assert Path(path).exists(), path

    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "config/observability/prometheus.yml" in compose
    assert "config/observability/alerts.yml" in compose
    assert "config/observability/loki-config.yml" in compose
    assert "config/observability/tempo.yml" in compose
    assert "config/observability/alertmanager.yml" in compose

    prometheus = Path("config/observability/prometheus.yml").read_text(encoding="utf-8")
    assert "rule_files" in prometheus
    assert "alerts.yml" in prometheus
    assert "alertmanagers:" in prometheus
    assert "scrape_configs:" in prometheus


def test_alert_catalog_covers_critical_operational_events() -> None:
    alerts = Path("config/observability/alerts.yml").read_text(encoding="utf-8")
    assert re.search(r"alert:\s*ExchangeConnectivityIssue", alerts)
    assert re.search(r"alert:\s*LLMQuotaBreach", alerts)
    assert re.search(r"alert:\s*RiskDrawdownBreach", alerts)
    assert re.search(r"alert:\s*ElevatedOrderFailures", alerts)
    assert re.search(r"alert:\s*IntegrityResyncEvents", alerts)
