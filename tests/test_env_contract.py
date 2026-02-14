from pathlib import Path


def test_env_example_exists() -> None:
    assert Path(".env.example").exists()


def test_env_validator_exists() -> None:
    assert Path("scripts/validate_env.py").exists()
