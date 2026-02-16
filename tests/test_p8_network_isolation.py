from __future__ import annotations

from pathlib import Path
import re


def test_compose_defines_public_and_internal_networks() -> None:
    content = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "networks:" in content
    assert re.search(r"^\s{2}public:\s*$", content, flags=re.MULTILINE)
    assert re.search(r"^\s{2}internal:\s*$", content, flags=re.MULTILINE)
    assert "internal: true" in content


def test_internal_services_do_not_publish_host_ports() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    internal_only_services = (
        "redis",
        "notification_worker",
        "prometheus",
        "alertmanager",
        "loki",
        "tempo",
    )
    for service_name in internal_only_services:
        block = _service_block(compose, service_name)
        assert "ports:" not in block, service_name


def test_rabbitmq_management_port_is_localhost_bound_only() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    rabbitmq = _service_block(compose, "rabbitmq")
    assert "ports:" in rabbitmq
    assert '127.0.0.1:15672:15672' in rabbitmq


def test_postgres_port_is_localhost_bound_only() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    postgres = _service_block(compose, "postgres_timescaledb")
    assert "ports:" in postgres
    assert '127.0.0.1:5432:5432' in postgres


def test_only_grafana_is_exposed_for_observability_surface() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    grafana = _service_block(compose, "grafana")
    assert "ports:" in grafana
    assert '127.0.0.1:3000:3000' in grafana


def _service_block(content: str, service_name: str) -> str:
    marker = f"  {service_name}:"
    start = content.find(marker)
    if start < 0:
        raise AssertionError(f"service block not found: {service_name}")

    remainder = content[start + len(marker) :]
    match = re.search(r"\n  [a-zA-Z0-9_]+:\n|\nvolumes:\n|\nnetworks:\n", remainder)
    if match is None:
        return remainder
    return remainder[: match.start()]
