from pathlib import Path


def test_runbook_files_exist() -> None:
    assert Path("docs/runbooks/AGENT.md").exists()
    assert Path("docs/runbooks/exchange-outage.md").exists()
    assert Path("docs/runbooks/llm-quota-breach.md").exists()
    assert Path("docs/runbooks/risk-incident.md").exists()


def test_exchange_outage_runbook_has_required_sections() -> None:
    content = Path("docs/runbooks/exchange-outage.md").read_text(encoding="utf-8")
    assert "Detection Signals" in content
    assert "Immediate Actions" in content
    assert "Escalation" in content
    assert "Recovery Validation" in content
    assert "Post-Incident Actions" in content


def test_quota_and_risk_runbooks_have_response_workflows() -> None:
    quota = Path("docs/runbooks/llm-quota-breach.md").read_text(encoding="utf-8")
    risk = Path("docs/runbooks/risk-incident.md").read_text(encoding="utf-8")
    for content in (quota, risk):
        assert "Detection Signals" in content
        assert "Immediate Actions" in content
        assert "Escalation" in content
        assert "Recovery Validation" in content
        assert "Post-Incident Actions" in content

