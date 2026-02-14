from pathlib import Path


def test_adr_exists() -> None:
    assert Path("docs/adr/0001-architecture-baseline.md").exists()
