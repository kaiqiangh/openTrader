from pathlib import Path


def test_ci_workflow_exists() -> None:
    assert Path(".github/workflows/ci.yml").exists()


def test_ci_workflow_has_go_job() -> None:
    content = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "go-checks:" in content


def test_ci_workflow_has_migration_check() -> None:
    content = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "alembic -c alembic.ini history" in content
