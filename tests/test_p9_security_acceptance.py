from __future__ import annotations

from pathlib import Path
import re
from fastapi.testclient import TestClient
import pytest

from services.api.app import create_app
from services.api.settings import APISettings
from services.api.state import build_default_state
from services.notification_service.settings import (
    NotificationSettingsError,
    load_notification_worker_settings,
)
from tests.jwt_test_helpers import encode_jwt_rs256, make_test_settings


def _settings() -> APISettings:
    return make_test_settings()


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


def test_p9_security_acceptance_rbac_enforcement() -> None:
    settings = _settings()
    app = create_app(
        settings=settings, state=build_default_state(default_mode=settings.default_mode)
    )
    client = TestClient(app)

    viewer_token = encode_jwt_rs256(subject="viewer", role="viewer", settings=settings)
    operator_token = encode_jwt_rs256(subject="operator", role="operator", settings=settings)

    assert client.get("/metadata").status_code == 401

    viewer_attempt = client.put(
        "/control/mode",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"mode": "REAL", "reason": "security acceptance"},
    )
    assert viewer_attempt.status_code == 403

    operator_attempt = client.put(
        "/control/mode",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"mode": "REAL", "reason": "security acceptance"},
    )
    assert operator_attempt.status_code == 200
    assert operator_attempt.json()["mode"] == "REAL"


def test_p9_security_acceptance_network_exposure_boundaries() -> None:
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
        assert "ports:" not in _service_block(compose, service_name), service_name

    grafana_block = _service_block(compose, "grafana")
    assert "ports:" in grafana_block
    assert "127.0.0.1:${GRAFANA_HOST_PORT:-3001}:3000" in grafana_block

    rabbitmq_block = _service_block(compose, "rabbitmq")
    assert "ports:" in rabbitmq_block
    assert "127.0.0.1:15672:15672" in rabbitmq_block

    postgres_block = _service_block(compose, "postgres_timescaledb")
    assert "ports:" in postgres_block
    assert "127.0.0.1:5432:5432" in postgres_block


def test_p9_security_acceptance_secret_placeholder_rejection() -> None:
    base_env = {
        "NOTIFY_ENABLED": "true",
        "NOTIFY_DEFAULT_GATEWAY": "telegram",
        "NOTIFICATION_DEFAULT_SEVERITY": "WARNING",
        "NOTIFY_QUEUE_NAME": "notify.events.raw",
        "NOTIFY_CONSUMER_BACKEND": "inmemory",
        "RABBITMQ_DEFAULT_USER": "guest",
        "RABBITMQ_DEFAULT_PASS": "guest",
        "NOTIFY_RABBITMQ_HTTP_API_URL": "http://rabbitmq:15672/api",
        "TELEGRAM_DEFAULT_CHAT_ID": "ops-channel",
        "TELEGRAM_BOT_TOKEN": "change_me",
    }

    with pytest.raises(NotificationSettingsError):
        load_notification_worker_settings(env=base_env)

    accepted_env = dict(base_env)
    accepted_env["TELEGRAM_BOT_TOKEN"] = "bot:real-ish-token"
    settings = load_notification_worker_settings(env=accepted_env)
    assert settings.telegram_bot_token == "bot:real-ish-token"
