from pathlib import Path


def test_smoke_script_exists_and_checks_compose_services() -> None:
    script = Path("scripts/smoke_test.py")
    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "REQUIRED_SERVICES" in content
    assert "docker compose up -d" in content or '"docker", "compose", "up", "-d"' in content
    assert "services.notification_service.worker" in content
    assert "services.api.app" in content


def test_makefile_exposes_smoke_target() -> None:
    content = Path("Makefile").read_text(encoding="utf-8")
    assert (
        ".PHONY: test lint fmt env-validate migrate-up migrate-down migrate-revision smoke"
        in content
    )
    assert "smoke:" in content
    assert "uv run python scripts/smoke_test.py" in content


def test_smoke_script_normalizes_rabbitmq_host_for_local_probe() -> None:
    content = Path("scripts/smoke_test.py").read_text(encoding="utf-8")
    assert "_resolve_rabbitmq_http_api_for_host" in content
    assert "127.0.0.1:15672" in content
    assert "execution.events/publish" in content
