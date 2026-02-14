from pathlib import Path


def test_makefile_exists() -> None:
    assert Path("Makefile").exists()


def test_readme_has_bootstrap_section() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "## Development Bootstrap" in readme
