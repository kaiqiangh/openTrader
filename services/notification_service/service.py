from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from services.notification_service.event_intake import NotificationEventIntake
from services.notification_service.gateway_dispatch import GatewayDispatcher
from services.notification_service.models import NotificationProcessingResult
from services.notification_service.policy_router import NotificationPolicyRouter


class NotificationService:
    """Runtime pipeline: event_intake -> policy_router -> gateway_dispatch."""

    def __init__(
        self,
        *,
        intake: NotificationEventIntake,
        policy_router: NotificationPolicyRouter,
        dispatcher: GatewayDispatcher,
    ) -> None:
        self.intake = intake
        self.policy_router = policy_router
        self.dispatcher = dispatcher

    async def process_envelope(
        self,
        envelope: Mapping[str, Any],
        *,
        now_seconds: float | None = None,
    ) -> NotificationProcessingResult:
        event = self.intake.normalize(envelope)
        current_seconds = now_seconds if now_seconds is not None else _utc_now_seconds()
        messages = self.policy_router.route(event=event, now_seconds=current_seconds)
        results = await self.dispatcher.dispatch(event=event, messages=messages)
        return NotificationProcessingResult(event=event, messages=messages, results=results)


def _utc_now_seconds() -> float:
    return datetime.now(timezone.utc).timestamp()
