from __future__ import annotations

from time import perf_counter
from typing import Any

from services.notification_service.publishers import NotificationEventBridge
from services.simulation_execution.engine import SimulationExecutionEngine, SimulationExecutionResult
from services.simulation_execution.metrics_tracing import SimulationExecutionMetrics, utc_now_iso
from services.simulation_execution.mode_routing import MOCK_ROUTING_KEY
from services.simulation_execution.safety_guard import MockModeSafetyGuard


class SimulationExecutionWorker:
    def __init__(
        self,
        *,
        broker: Any,
        engine: SimulationExecutionEngine | None = None,
        safety_guard: MockModeSafetyGuard | None = None,
        metrics: SimulationExecutionMetrics | None = None,
        notification_bridge: NotificationEventBridge | None = None,
        consume_queue: str = MOCK_ROUTING_KEY,
        publish_routing_key: str = "oms.order.mock",
    ) -> None:
        self.broker = broker
        self.engine = engine or SimulationExecutionEngine()
        self.safety_guard = safety_guard or MockModeSafetyGuard()
        self.metrics = metrics or SimulationExecutionMetrics()
        self.notification_bridge = notification_bridge
        self.consume_queue = consume_queue
        self.publish_routing_key = publish_routing_key

    async def run_once(self, *, timeout_seconds: float | None = 0.0) -> SimulationExecutionResult | None:
        envelope = await self.broker.consume(
            queue_name=self.consume_queue,
            timeout_seconds=timeout_seconds,
        )
        if envelope is None:
            return None

        trace_id = str(envelope.get("trace_id", "unknown"))
        decision_id = str(envelope.get("decision_id", "unknown"))
        mode = str(envelope.get("mode", "unknown"))
        stage = "simulation_execution_worker.run_once"
        started_at = utc_now_iso()
        started = perf_counter()
        try:
            self.safety_guard.assert_mock_intent(
                mode=mode,
                queue_name=self.consume_queue,
            )
            result = self.engine.execute_intent(envelope)
            for event in result.events:
                await self.broker.publish(routing_key=self.publish_routing_key, message=event)
                if self.notification_bridge is not None:
                    await self.notification_bridge.publish_oms_event(event)
            latency_ms = (perf_counter() - started) * 1000.0
            self.metrics.record_success(
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                stage=stage,
                latency_ms=latency_ms,
                events_published=len(result.events),
                started_at=started_at,
                completed_at=utc_now_iso(),
            )
            return result
        except Exception as exc:
            latency_ms = (perf_counter() - started) * 1000.0
            self.metrics.record_failure(
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                stage=stage,
                latency_ms=latency_ms,
                error_type=type(exc).__name__,
                started_at=started_at,
                completed_at=utc_now_iso(),
            )
            raise
