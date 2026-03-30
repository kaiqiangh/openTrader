from __future__ import annotations

import pytest

from services.simulation_execution.safety_guard import (
    MockModeSafetyGuard,
    SimulationSafetyViolation,
)


def test_mock_mode_safety_guard_accepts_mock_queue() -> None:
    guard = MockModeSafetyGuard()
    guard.assert_mock_intent(mode="MOCK", queue_name="execution.intent.mock")


def test_mock_mode_safety_guard_rejects_real_mode() -> None:
    guard = MockModeSafetyGuard()

    with pytest.raises(SimulationSafetyViolation):
        guard.assert_mock_intent(mode="REAL", queue_name="execution.intent.mock")


def test_mock_mode_safety_guard_blocks_live_order_endpoint_in_mock_mode() -> None:
    guard = MockModeSafetyGuard()

    with pytest.raises(SimulationSafetyViolation):
        guard.assert_endpoint_allowed(
            endpoint="https://api.binance.com/api/v3/order",
            mode="MOCK",
        )


def test_mock_mode_safety_guard_allows_market_data_endpoint() -> None:
    guard = MockModeSafetyGuard()
    guard.assert_endpoint_allowed(endpoint="https://api.binance.com/api/v3/depth", mode="MOCK")
