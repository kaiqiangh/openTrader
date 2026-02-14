from __future__ import annotations

from typing import Any

from services.simulation_execution.engine import SimulationExecutionEngine, SimulationExecutionResult
from services.simulation_execution.mode_routing import MOCK_ROUTING_KEY
from services.simulation_execution.safety_guard import MockModeSafetyGuard


class SimulationExecutionWorker:
    def __init__(
        self,
        *,
        broker: Any,
        engine: SimulationExecutionEngine | None = None,
        safety_guard: MockModeSafetyGuard | None = None,
        consume_queue: str = MOCK_ROUTING_KEY,
        publish_routing_key: str = "oms.order.mock",
    ) -> None:
        self.broker = broker
        self.engine = engine or SimulationExecutionEngine()
        self.safety_guard = safety_guard or MockModeSafetyGuard()
        self.consume_queue = consume_queue
        self.publish_routing_key = publish_routing_key

    async def run_once(self, *, timeout_seconds: float | None = 0.0) -> SimulationExecutionResult | None:
        envelope = await self.broker.consume(
            queue_name=self.consume_queue,
            timeout_seconds=timeout_seconds,
        )
        if envelope is None:
            return None

        self.safety_guard.assert_mock_intent(
            mode=str(envelope.get("mode", "")),
            queue_name=self.consume_queue,
        )
        result = self.engine.execute_intent(envelope)
        for event in result.events:
            await self.broker.publish(routing_key=self.publish_routing_key, message=event)
        return result
