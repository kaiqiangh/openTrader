from pathlib import Path


def test_docker_compose_exists() -> None:
    assert Path("docker-compose.yml").exists()


def test_docker_compose_has_core_services() -> None:
    content = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "postgres_timescaledb:" in content
    assert "redis:" in content
    assert "rabbitmq:" in content


def test_docker_compose_has_networks_and_volumes() -> None:
    content = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "networks:" in content
    assert "internal:" in content
    assert "volumes:" in content


def test_alembic_scaffold_exists() -> None:
    assert Path("alembic.ini").exists()
    assert Path("migrations/env.py").exists()
    assert Path("migrations/script.py.mako").exists()
    assert Path("migrations/versions").exists()


def test_makefile_has_migration_targets() -> None:
    content = Path("Makefile").read_text(encoding="utf-8")
    assert "migrate-up:" in content
    assert "migrate-down:" in content
