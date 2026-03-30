"""Runtime workers package — re-exports for backward compatibility."""

from services.workers.runtime_pipeline import (
    AgentOrchestratorRuntimeWorker,
    MarketIngestionRuntimeWorker,
    RuntimeIntegrationGate,
)

__all__ = [
    # From runtime_pipeline (existing)
    "MarketIngestionRuntimeWorker",
    "AgentOrchestratorRuntimeWorker",
    "RuntimeIntegrationGate",
    # Settings
    "RuntimeWorkerSettings",
    "RuntimeWorkerBuildResult",
    "RuntimeWorkerRunner",
    "load_runtime_worker_settings",
    # Worker runners
    "MarketWorkerRunner",
    "OrchestratorWorkerRunner",
    "SimulationWorkerRunner",
    "OMSLifecycleWorkerRunner",
    "NewsWorkerRunner",
    # Builders
    "build_runtime_broker",
    "build_runtime_worker",
    # Loop
    "run_worker_loop",
]


def __getattr__(name: str):  # pragma: no cover - compatibility shim for lazy imports
    _lazy = {
        # Settings
        "RuntimeWorkerSettings": ("services.workers.settings", "RuntimeWorkerSettings"),
        "RuntimeWorkerBuildResult": ("services.workers.settings", "RuntimeWorkerBuildResult"),
        "RuntimeWorkerRunner": ("services.workers.settings", "RuntimeWorkerRunner"),
        "load_runtime_worker_settings": (
            "services.workers.settings",
            "load_runtime_worker_settings",
        ),
        # Worker runners
        "MarketWorkerRunner": ("services.workers.market", "MarketWorkerRunner"),
        "OrchestratorWorkerRunner": ("services.workers.orchestrator", "OrchestratorWorkerRunner"),
        "SimulationWorkerRunner": ("services.workers.simulation", "SimulationWorkerRunner"),
        "OMSLifecycleWorkerRunner": ("services.workers.oms_lifecycle", "OMSLifecycleWorkerRunner"),
        "NewsWorkerRunner": ("services.workers.news", "NewsWorkerRunner"),
        # Builders
        "build_runtime_broker": ("services.workers.builders", "build_runtime_broker"),
        "build_runtime_worker": ("services.workers.builders", "build_runtime_worker"),
        # Loop
        "run_worker_loop": ("services.workers.main", "run_worker_loop"),
    }
    if name in _lazy:
        module_path, attr_name = _lazy[name]
        from importlib import import_module

        mod = import_module(module_path)
        return getattr(mod, attr_name)
    raise AttributeError(name)
