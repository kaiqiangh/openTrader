from pathlib import Path


def test_go_module_exists() -> None:
    assert Path("services/real_execution_go/go.mod").exists()


def test_go_main_exists() -> None:
    assert Path("services/real_execution_go/main.go").exists()
