from pathlib import Path


def test_go_mod_declares_supported_version() -> None:
    content = Path("services/real_execution_go/go.mod").read_text(encoding="utf-8")
    assert "go 1.21" in content
