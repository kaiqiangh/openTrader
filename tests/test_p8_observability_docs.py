from pathlib import Path
import re


def test_observability_runtime_files_exist() -> None:
    assert Path("services/shared/runtime/structured_logging.py").exists()
    assert Path("services/shared/runtime/prometheus.py").exists()
    assert Path("services/shared/runtime/trace_context.py").exists()
    assert Path("services/real_execution_go/internal/tracing/tracecontext.go").exists()


def test_readme_mentions_observability_baseline() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    assert "services/shared/runtime/structured_logging.py" in content
    assert "services/shared/runtime/prometheus.py" in content
    assert "services/shared/runtime/trace_context.py" in content
    assert "config/observability/prometheus.yml" in content
    assert "config/observability/alerts.yml" in content
    assert "services/shared/runtime/key_encryption.py" in content
    assert "services/shared/runtime/exchange_credentials.py" in content
    assert "/metrics" in content


def test_implementation_plan_marks_p8_001_to_p8_009_done() -> None:
    content = Path("docs/IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")
    assert re.search(r"\| P8-001 \|.*\| DONE \|", content)
    assert re.search(r"\| P8-002 \|.*\| DONE \|", content)
    assert re.search(r"\| P8-003 \|.*\| DONE \|", content)
    assert re.search(r"\| P8-004 \|.*\| DONE \|", content)
    assert re.search(r"\| P8-005 \|.*\| DONE \|", content)
    assert re.search(r"\| P8-006 \|.*\| DONE \|", content)
    assert re.search(r"\| P8-007 \|.*\| DONE \|", content)
    assert re.search(r"\| P8-008 \|.*\| DONE \|", content)
    assert re.search(r"\| P8-009 \|.*\| DONE \|", content)
