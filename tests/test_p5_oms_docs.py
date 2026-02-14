from pathlib import Path


def test_oms_modules_exist() -> None:
    assert Path("services/oms/state_machine.py").exists()
    assert Path("services/oms/fill_reconciliation.py").exists()
    assert Path("services/oms/position_engine.py").exists()
    assert Path("services/oms/portfolio_snapshot.py").exists()
    assert Path("services/oms/risk_rules.py").exists()
    assert Path("services/oms/risk_guards.py").exists()
    assert Path("services/oms/risk_controls.py").exists()
    assert Path("services/oms/risk_policy.py").exists()
    assert Path("services/oms/risk_observability.py").exists()


def test_readme_mentions_p5_oms_modules() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "services/oms/fill_reconciliation.py" in content
    assert "services/oms/position_engine.py" in content
    assert "services/oms/portfolio_snapshot.py" in content
    assert "services/oms/risk_rules.py" in content
    assert "services/oms/risk_guards.py" in content
    assert "services/oms/risk_controls.py" in content
    assert "services/oms/risk_policy.py" in content
    assert "services/oms/risk_observability.py" in content


def test_implementation_plan_marks_p5_002_to_p5_009_done() -> None:
    content = Path("docs/IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")
    assert "| P5-002 |" in content and "| DONE |" in content
    assert "| P5-003 |" in content and "| DONE |" in content
    assert "| P5-004 |" in content and "| DONE |" in content
    assert "| P5-005 |" in content and "| DONE |" in content
    assert "| P5-006 |" in content and "| DONE |" in content
    assert "| P5-007 |" in content and "| DONE |" in content
    assert "| P5-008 |" in content and "| DONE |" in content
    assert "| P5-009 |" in content and "| DONE |" in content
