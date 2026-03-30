from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Protocol

from services.news_summarizer.summarizer_service import NewsSummaryArtifact
from services.shared.contracts.message_envelope import validate_envelope


class ContextEnvelopePublisher(Protocol):
    async def publish(self, *, routing_key: str, message: dict[str, Any]) -> Any: ...


class NewsContextInjectionBridge:
    """Publishes summary context envelopes and injects summary fields into market payloads."""

    def __init__(
        self,
        *,
        publisher: ContextEnvelopePublisher | None,
        context_routing_key: str = "strategy.context.news",
        service_name: str = "news_summarizer",
    ) -> None:
        self._publisher = publisher
        self.context_routing_key = context_routing_key
        self.service_name = service_name

    async def publish_summary_context(
        self,
        *,
        summary: NewsSummaryArtifact,
        strategy_id: str,
        mode: str,
        trace_id: str,
        decision_id: str,
        sentiment: float,
        source_count: int,
        is_fallback: bool | None = None,
    ) -> dict[str, Any]:
        if self._publisher is None:
            raise RuntimeError("publisher is not configured")

        fallback = (
            bool(is_fallback)
            if is_fallback is not None
            else (summary.summary_text == "news_unavailable")
        )
        payload = {
            "strategy_id": strategy_id,
            "symbol_scope": summary.symbol_scope,
            "window_start": summary.window_start,
            "window_end": summary.window_end,
            "summary_id": summary.summary_id,
            "summary_text": summary.summary_text,
            "token_count": summary.token_count,
            "generated_at": summary.generated_at,
            "source_news_ids": list(summary.source_news_ids),
            "news": {
                "summary": summary.summary_text,
                "sentiment": float(sentiment),
                "source_count": max(0, int(source_count)),
                "is_fallback": fallback,
            },
        }

        envelope = {
            "trace_id": trace_id,
            "decision_id": decision_id,
            "mode": mode,
            "idempotency_key": f"news.context:{summary.summary_id}:{strategy_id}",
            "event_type": "news.context.summary_ready",
            "emitted_at": _utc_now_iso(),
            "payload": payload,
            "service": self.service_name,
        }
        validate_envelope(envelope)
        await self._publisher.publish(routing_key=self.context_routing_key, message=envelope)
        return envelope

    @staticmethod
    def inject_into_market_payload(
        *,
        market_payload: Mapping[str, Any],
        summary: NewsSummaryArtifact,
        sentiment: float,
        source_count: int,
        is_fallback: bool | None = None,
    ) -> dict[str, Any]:
        payload = dict(market_payload)
        fallback = (
            bool(is_fallback)
            if is_fallback is not None
            else (summary.summary_text == "news_unavailable")
        )
        payload["news"] = {
            "summary": summary.summary_text,
            "sentiment": float(sentiment),
            "source_count": max(0, int(source_count)),
            "is_fallback": fallback,
            "summary_id": summary.summary_id,
            "window_start": summary.window_start,
            "window_end": summary.window_end,
            "generated_at": summary.generated_at,
        }
        return payload


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
