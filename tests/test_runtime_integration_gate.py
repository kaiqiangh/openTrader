from pathlib import Path


def test_runtime_integration_gate_script_exists_and_writes_report() -> None:
    script = Path("scripts/runtime_integration_gate.py")
    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert 'make", "smoke"' in content
    assert "artifacts/runtime_integration_gate/latest.json" in content
    assert "overall_status" in content


def test_makefile_exposes_runtime_gate_target() -> None:
    content = Path("Makefile").read_text(encoding="utf-8")
    assert "runtime-gate" in content
    assert "uv run python scripts/runtime_integration_gate.py" in content
