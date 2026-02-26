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
    assert Path("apps/dashboard/src/components/dashboard-client.js").exists()
    assert Path("apps/dashboard/app/globals.css").exists()
    assert Path("services/notification_service/models.py").exists()
    assert Path("services/notification_service/event_intake.py").exists()
    assert Path("services/notification_service/policy_router.py").exists()
    assert Path("services/notification_service/gateway_dispatch.py").exists()
    assert Path("services/notification_service/service.py").exists()
    assert Path("services/notification_service/publishers.py").exists()
    assert Path("services/notification_service/telegram_gateway.py").exists()
    assert Path("services/notification_service/observability.py").exists()
    assert Path("services/notification_service/settings.py").exists()
    assert Path("services/notification_service/worker.py").exists()


def test_readme_mentions_api_control_plane_baseline() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "services/api/app.py" in content
    assert "services/api/auth.py" in content
    assert "services/api/routers/control.py" in content
    assert "services/api/routers/ops.py" in content
    assert "services/api/routers/governance.py" in content
    assert "services/api/routers/replay.py" in content
    assert "services/api/routers/dashboard.py" in content
    assert "apps/dashboard/src/components/dashboard-client.js" in content
    assert "apps/dashboard/app/globals.css" in content
    assert "services/notification_service/models.py" in content
    assert "services/notification_service/publishers.py" in content
    assert "services/notification_service/telegram_gateway.py" in content
    assert "services/notification_service/observability.py" in content
    assert "services/notification_service/settings.py" in content
    assert "services/notification_service/worker.py" in content


def test_implementation_plan_marks_p7_001_to_p7_018_done() -> None:
    content = Path("docs/IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")
    assert re.search(r"\| P7-001 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-002 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-003 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-004 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-005 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-006 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-007 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-008 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-009 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-010 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-011 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-012 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-013 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-014 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-015 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-016 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-017 \|.*\| DONE \|", content)
    assert re.search(r"\| P7-018 \|.*\| DONE \|", content)
