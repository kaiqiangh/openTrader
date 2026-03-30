"""Simulation (paper trading) worker runner."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.simulation_execution.worker import SimulationExecutionWorker


class SimulationWorkerRunner:
    def __init__(self, *, worker: SimulationExecutionWorker) -> None:
        self.worker = worker
        self._last_activity: dict[str, Any] = {}

    async def run_once(self, *, timeout_seconds: float) -> bool:
        result = await self.worker.run_once(timeout_seconds=timeout_seconds)
        if result is None:
            self._last_activity = {"event": "no_mock_intent"}
            return False
        self._last_activity = {
            "event": "simulation_order_executed",
            "order_id": result.order_id,
            "status": result.status,
            "action": result.action,
            "symbol": result.symbol,
            "quantity": result.quantity,
            "fill_price": result.fill_price,
            "fee_paid": result.fee_paid,
            "events_published": len(result.events),
        }
        metrics_snapshot = self.worker.metrics.snapshot()
        totals = metrics_snapshot.get("totals")
        if isinstance(totals, Mapping):
            self._last_activity["metrics_totals"] = dict(totals)
        return True

    def activity_snapshot(self) -> dict[str, Any]:
        return dict(self._last_activity)
