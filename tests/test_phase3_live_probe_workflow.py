from pathlib import Path


def test_phase3_live_runtime_probe_script_exists_and_writes_expected_artifact() -> None:
    script = Path("scripts/live_runtime_probe.py")
    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "scripts/mock_realtime_workflow_test.py" in content
    assert "artifacts/live_runtime_probe/latest.json" in content
    assert "overall_status" in content


def test_phase3_makefile_exposes_live_probe_target() -> None:
    content = Path("Makefile").read_text(encoding="utf-8")
    assert "live-probe" in content
    assert "uv run python scripts/live_runtime_probe.py" in content


def test_phase3_nightly_live_probe_workflow_exists_and_is_scheduled() -> None:
    workflow = Path(".github/workflows/nightly-live-probe.yml")
    assert workflow.exists()
    content = workflow.read_text(encoding="utf-8")
    assert "schedule:" in content
    assert "workflow_dispatch:" in content
    assert "cron:" in content
    assert "scripts/live_runtime_probe.py" in content
    assert "upload-artifact" in content
