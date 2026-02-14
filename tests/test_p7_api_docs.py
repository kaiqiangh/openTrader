from pathlib import Path
import re


def test_api_control_plane_files_exist() -> None:
    assert Path("services/api/app.py").exists()
    assert Path("services/api/auth.py").exists()
    assert Path("services/api/settings.py").exists()
    assert Path("services/api/state.py").exists()
    assert Path("services/api/models.py").exists()
    assert Path("services/api/routers/system.py").exists()
    assert Path("services/api/routers/control.py").exists()
    assert Path("services/api/routers/ops.py").exists()
    assert Path("services/api/routers/governance.py").exists()
    assert Path("services/api/routers/replay.py").exists()
    assert Path("services/api/routers/dashboard.py").exists()


def test_readme_mentions_api_control_plane_baseline() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "services/api/app.py" in content
    assert "services/api/auth.py" in content
    assert "services/api/routers/control.py" in content
    assert "services/api/routers/ops.py" in content
    assert "services/api/routers/governance.py" in content
    assert "services/api/routers/replay.py" in content
    assert "services/api/routers/dashboard.py" in content


def test_implementation_plan_marks_p7_001_to_p7_006_done() -> None:
    content = Path("docs/IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")
    assert re.search(r"\| P7-001 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-002 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-003 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-004 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-005 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-006 \|.*\| DONE \|", content)
