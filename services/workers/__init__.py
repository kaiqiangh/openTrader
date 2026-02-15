from services.workers.runtime_pipeline import (
    AgentOrchestratorRuntimeWorker,
    MarketIngestionRuntimeWorker,
    RuntimeIntegrationGate,
)

__all__ = [
    "MarketIngestionRuntimeWorker",
    "AgentOrchestratorRuntimeWorker",
    "RuntimeIntegrationGate",
    "build_runtime_broker",
    "build_runtime_worker",
    "load_runtime_worker_settings",
    "run_worker_loop",
]


def __getattr__(name: str):  # pragma: no cover - compatibility shim for lazy imports
    if name in {
        "build_runtime_broker",
        "build_runtime_worker",
        "load_runtime_worker_settings",
        "run_worker_loop",
    }:
        from services.workers.main import (
            build_runtime_broker,
            build_runtime_worker,
            load_runtime_worker_settings,
            run_worker_loop,
        )

        mapping = {
            "build_runtime_broker": build_runtime_broker,
            "build_runtime_worker": build_runtime_worker,
            "load_runtime_worker_settings": load_runtime_worker_settings,
            "run_worker_loop": run_worker_loop,
        }
        return mapping[name]
    raise AttributeError(name)
