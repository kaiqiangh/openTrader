from pathlib import Path


def test_control_plane_notification_migration_exists() -> None:
    assert Path("migrations/versions/20260219_0007_control_plane_notification_state.py").exists()


def test_control_plane_notification_migration_has_required_tables() -> None:
    content = Path(
        "migrations/versions/20260219_0007_control_plane_notification_state.py"
    ).read_text(encoding="utf-8")
    assert "strategy_runtime_state" in content
    assert "mode_audit_events" in content
    assert "notification_preferences" in content
    assert "notification_deliveries" in content
    assert "notification_trace_spans" in content


def test_readme_mentions_control_plane_notification_migration() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "20260219_0007_control_plane_notification_state.py" in content
