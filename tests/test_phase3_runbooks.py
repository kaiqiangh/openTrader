from pathlib import Path


def test_phase3_runbooks_exist() -> None:
    assert Path("docs/runbooks/stream-health-incident.md").exists()
    assert Path("docs/runbooks/nightly-live-probe.md").exists()


def test_phase3_stream_health_runbook_has_required_sections() -> None:
    content = Path("docs/runbooks/stream-health-incident.md").read_text(encoding="utf-8")
    for section in (
        "Detection Signals",
        "Immediate Actions",
        "Escalation",
        "Recovery Validation",
        "Post-Incident Actions",
    ):
        assert section in content


def test_phase3_nightly_probe_runbook_has_required_sections() -> None:
    content = Path("docs/runbooks/nightly-live-probe.md").read_text(encoding="utf-8")
    for section in (
        "Detection Signals",
        "Immediate Actions",
        "Escalation",
        "Recovery Validation",
        "Post-Incident Actions",
    ):
        assert section in content
