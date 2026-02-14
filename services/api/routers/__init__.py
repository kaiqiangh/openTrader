from services.api.routers.control import router as control_router
from services.api.routers.ops import router as ops_router
from services.api.routers.system import router as system_router

__all__ = ["system_router", "control_router", "ops_router"]
