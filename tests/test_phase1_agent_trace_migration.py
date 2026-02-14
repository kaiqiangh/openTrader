from pathlib import Path


def test_agent_trace_migration_exists() -> None:
    migration = Path("migrations/versions/20260214_0003_agent_trace_schema.py")
    assert migration.exists()


def test_agent_trace_migration_has_required_tables() -> None:
    content = Path("migrations/versions/20260214_0003_agent_trace_schema.py").read_text(
        encoding="utf-8"
    )
    assert "decision_traces" in content
    assert "agent_runs" in content
    assert "agent_messages" in content


def test_agent_trace_migration_has_fk_and_indexes() -> None:
    content = Path("migrations/versions/20260214_0003_agent_trace_schema.py").read_text(
        encoding="utf-8"
    )
    assert 'sa.ForeignKey("decision_traces.decision_id")' in content
    assert 'sa.ForeignKey("agent_runs.agent_run_id")' in content
    assert "idx_agent_runs_decision_id" in content
    assert "idx_agent_messages_agent_run_id_created_at" in content


def test_readme_mentions_agent_trace_migration() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "20260214_0003_agent_trace_schema.py" in content
