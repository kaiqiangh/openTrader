from pathlib import Path
import re


def test_p9_validation_artifacts_exist() -> None:
    assert Path("tests/test_p9_e2e_mock_flow.py").exists()
    assert Path("tests/test_p9_e2e_real_flow.py").exists()
    assert Path("tests/test_p9_mode_isolation.py").exists()
    assert Path("tests/test_p9_replay_determinism.py").exists()
    assert Path("tests/test_p9_performance_benchmarks.py").exists()
    assert Path("tests/test_p9_chaos_resilience.py").exists()
    assert Path("tests/test_p9_data_integrity_audits.py").exists()
    assert Path("tests/test_p9_security_acceptance.py").exists()
    assert Path("docs/runtime/p9-validation-2026-02-14.md").exists()
    assert Path("docs/runtime/p9-replay-determinism-2026-02-15.md").exists()
    assert Path("docs/runtime/p9-performance-benchmark-2026-02-15.md").exists()
    assert Path("docs/runtime/p9-resilience-drills-2026-02-15.md").exists()
    assert Path("docs/runtime/p9-data-integrity-audit-2026-02-15.md").exists()
    assert Path("docs/runtime/p9-security-acceptance-2026-02-15.md").exists()
    assert Path("docs/release/p9-release-checklist-2026-02-15.md").exists()
    assert Path("docs/release/p9-cutover-and-rollback-2026-02-15.md").exists()
    assert Path("docs/release/p9-post-phase-handoff-pack-2026-02-15.md").exists()
    assert Path("docs/learning/2026-02-14-p9-validation-instincts.md").exists()
    assert Path("docs/learning/2026-02-15-p9-004-p9-006-instincts.md").exists()
    assert Path("docs/learning/2026-02-15-p9-007-p9-009-instincts.md").exists()


def test_readme_mentions_p9_validation_suite() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "tests/test_p9_e2e_mock_flow.py" in content
    assert "tests/test_p9_e2e_real_flow.py" in content
    assert "tests/test_p9_mode_isolation.py" in content
    assert "docs/runtime/p9-validation-2026-02-14.md" in content
    assert "tests/test_p9_replay_determinism.py" in content
    assert "tests/test_p9_performance_benchmarks.py" in content
    assert "tests/test_p9_chaos_resilience.py" in content
    assert "docs/runtime/p9-replay-determinism-2026-02-15.md" in content
    assert "docs/runtime/p9-performance-benchmark-2026-02-15.md" in content
    assert "docs/runtime/p9-resilience-drills-2026-02-15.md" in content
    assert "tests/test_p9_data_integrity_audits.py" in content
    assert "tests/test_p9_security_acceptance.py" in content
    assert "docs/runtime/p9-data-integrity-audit-2026-02-15.md" in content
    assert "docs/runtime/p9-security-acceptance-2026-02-15.md" in content
    assert "docs/release/p9-release-checklist-2026-02-15.md" in content
    assert "docs/release/p9-cutover-and-rollback-2026-02-15.md" in content
    assert "docs/release/p9-post-phase-handoff-pack-2026-02-15.md" in content


def test_implementation_plan_marks_p9_001_to_p9_009_done() -> None:
    content = Path("docs/IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")
    assert re.search(r"\| P9-001 \|.*\| DONE \|", content)
    assert re.search(r"\| P9-002 \|.*\| DONE \|", content)
    assert re.search(r"\| P9-003 \|.*\| DONE \|", content)
    assert re.search(r"\| P9-004 \|.*\| DONE \|", content)
    assert re.search(r"\| P9-005 \|.*\| DONE \|", content)
    assert re.search(r"\| P9-006 \|.*\| DONE \|", content)
    assert re.search(r"\| P9-007 \|.*\| DONE \|", content)
    assert re.search(r"\| P9-008 \|.*\| DONE \|", content)
    assert re.search(r"\| P9-009 \|.*\| DONE \|", content)
    assert "1. Populate owner names for all `TBD` fields in `docs/release/p9-post-phase-handoff-pack-2026-02-15.md`." in content
    assert "2. Execute hypercare checklist windows and track status in war-room channel." in content
    assert "3. Convert `BL-001..BL-007` triage items into sprint tickets with owners/dates." in content
