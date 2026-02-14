from pathlib import Path

REQUIRED_DIRS = [
    "services/api",
    "services/market_ingestion",
    "services/integrity_service",
    "services/agent_orchestrator",
    "services/llm_gateway",
    "services/simulation_execution",
    "services/real_execution_go",
    "services/oms",
    "services/news_ingestion",
    "services/news_summarizer",
    "services/workers",
]


def test_required_service_directories_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    missing = [d for d in REQUIRED_DIRS if not (root / d).exists()]
    assert not missing, f"Missing directories: {missing}"
