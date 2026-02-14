from pathlib import Path


def test_pyproject_declares_python_313() -> None:
    content = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.13"' in content


def test_python_version_file_exists() -> None:
    assert Path(".python-version").exists()
