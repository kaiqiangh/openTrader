from services.api.routers.control import router as control_router
from services.api.routers.dashboard import router as dashboard_router
from services.api.routers.governance import router as governance_router
from services.api.routers.internal import router as internal_router
from services.api.routers.ops import router as ops_router
from services.api.routers.replay import router as replay_router
from services.api.routers.system import router as system_router

__all__ = [
    "system_router",
    "control_router",
    "internal_router",
    "ops_router",
    "governance_router",
    "replay_router",
    "dashboard_router",
]
