from pathlib import Path
import re


def test_p9_validation_artifacts_exist() -> None:
    assert Path("tests/test_p9_e2e_mock_flow.py").exists()
    assert Path("tests/test_p9_e2e_real_flow.py").exists()
    assert Path("tests/test_p9_mode_isolation.py").exists()
    assert Path("docs/runtime/p9-validation-2026-02-14.md").exists()
    assert Path("docs/learning/2026-02-14-p9-validation-instincts.md").exists()


def test_readme_mentions_p9_validation_suite() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "tests/test_p9_e2e_mock_flow.py" in content
    assert "tests/test_p9_e2e_real_flow.py" in content
    assert "tests/test_p9_mode_isolation.py" in content
    assert "docs/runtime/p9-validation-2026-02-14.md" in content


def test_implementation_plan_marks_p9_001_to_p9_003_done() -> None:
    content = Path("docs/IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")
    assert re.search(r"\| P9-001 \|.*\| DONE \|", content)
    assert re.search(r"\| P9-002 \|.*\| DONE \|", content)
    assert re.search(r"\| P9-003 \|.*\| DONE \|", content)
    assert "1. Start `P9-004` replay determinism tests" in content
    assert "2. Start `P9-005` performance tests" in content
    assert "3. Start `P9-006` chaos/resilience drills" in content
