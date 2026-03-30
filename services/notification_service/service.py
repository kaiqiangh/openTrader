from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from services.notification_service.event_intake import NotificationEventIntake
from services.notification_service.gateway_dispatch import GatewayDispatcher
from services.notification_service.observability import (
    NotificationObservabilityCollector,
    utc_now_iso,
)
from services.notification_service.models import NotificationProcessingResult
from services.notification_service.policy_router import NotificationPolicyRouter


_PersistFn = Callable[[NotificationProcessingResult], None]


class NotificationService:
    """Runtime pipeline: event_intake -> policy_router -> gateway_dispatch."""

    def __init__(
        self,
        *,
        intake: NotificationEventIntake,
        policy_router: NotificationPolicyRouter,
        dispatcher: GatewayDispatcher,
        observability: NotificationObservabilityCollector | None = None,
        persist_fn: _PersistFn | None = None,
    ) -> None:
        self.intake = intake
        self.policy_router = policy_router
        self.dispatcher = dispatcher
        self.observability = observability
        self._persist_fn = persist_fn

    async def process_envelope(
        self,
        envelope: Mapping[str, Any],
        *,
        now_seconds: float | None = None,
    ) -> NotificationProcessingResult:
        event = self.intake.normalize(envelope)
        if self.observability is not None:
            self.observability.record_event_received()

        current_seconds = now_seconds if now_seconds is not None else _utc_now_seconds()

        before_suppression = self.policy_router.suppression_counts()
        route_started = perf_counter()
        route_started_at = utc_now_iso()
        messages = self.policy_router.route(event=event, now_seconds=current_seconds)
        route_completed_at = utc_now_iso()
        route_latency_ms = (perf_counter() - route_started) * 1000.0
        after_suppression = self.policy_router.suppression_counts()
        suppression_delta = _delta_counts(before=before_suppression, after=after_suppression)
        if self.observability is not None:
            self.observability.record_policy_result(
                event=event,
                messages_count=len(messages),
                suppression_delta=suppression_delta,
                latency_ms=route_latency_ms,
                started_at=route_started_at,
                completed_at=route_completed_at,
            )

        dispatch_started = perf_counter()
        dispatch_started_at = utc_now_iso()
        dlq_before = len(self.dispatcher.dlq_items())
        results = await self.dispatcher.dispatch(event=event, messages=messages)
        dispatch_completed_at = utc_now_iso()
        dispatch_latency_ms = (perf_counter() - dispatch_started) * 1000.0
        dlq_after = len(self.dispatcher.dlq_items())
        if self.observability is not None:
            self.observability.record_dispatch_result(
                event=event,
                results=results,
                dlq_delta=max(0, dlq_after - dlq_before),
                latency_ms=dispatch_latency_ms,
                started_at=dispatch_started_at,
                completed_at=dispatch_completed_at,
            )

        processing_result = NotificationProcessingResult(
            event=event, messages=messages, results=results
        )

        if self._persist_fn is not None:
            try:
                self._persist_fn(processing_result)
            except Exception:
                pass  # persistence failure must not break the notification pipeline

        return processing_result


def _utc_now_seconds() -> float:
    return datetime.now(timezone.utc).timestamp()


def _delta_counts(*, before: Mapping[str, int], after: Mapping[str, int]) -> dict[str, int]:
    keys = set(before) | set(after)
    return {key: max(0, int(after.get(key, 0)) - int(before.get(key, 0))) for key in keys}
