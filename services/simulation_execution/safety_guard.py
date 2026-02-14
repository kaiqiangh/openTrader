from __future__ import annotations

from typing import Iterable


class SimulationSafetyViolation(RuntimeError):
    """Raised when MOCK-mode safety policy is violated."""


class MockModeSafetyGuard:
    def __init__(self, *, forbidden_live_markers: Iterable[str] | None = None) -> None:
        self.forbidden_live_markers = tuple(
            marker.lower()
            for marker in (
                forbidden_live_markers
                or (
                    "/api/v3/order",
                    "/api/v3/order/test",
                    "/api/mix/v1/order",
                )
            )
        )

    def assert_mock_intent(self, *, mode: str, queue_name: str) -> None:
        normalized = mode.upper()
        if normalized != "MOCK":
            raise SimulationSafetyViolation(f"Simulation worker accepts MOCK mode only, got {mode}")
        if queue_name != "execution.intent.mock":
            raise SimulationSafetyViolation(
                "Simulation worker must consume execution.intent.mock queue only"
            )

    def assert_endpoint_allowed(self, *, endpoint: str, mode: str) -> None:
        if mode.upper() != "MOCK":
            return
        endpoint_lc = endpoint.lower()
        if any(marker in endpoint_lc for marker in self.forbidden_live_markers):
            raise SimulationSafetyViolation(
                f"MOCK-mode attempted live order endpoint access: {endpoint}"
            )
