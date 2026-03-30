from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from services.news_summarizer.summarizer_service import NewsSummaryArtifact
from services.shared.contracts.message_envelope import validate_envelope


@dataclass(frozen=True, slots=True)
class NewsResilienceAlert:
    event_type: str
    severity: str
    reason: str
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class NewsResilienceDecision:
    degraded: bool
    reason: str
    news_payload: dict[str, Any]
    alerts: tuple[NewsResilienceAlert, ...]


class AlertPublisher(Protocol):
    async def publish(self, *, routing_key: str, message: dict[str, Any]) -> Any: ...


class NewsResiliencePolicy:
    """Applies staleness/fallback policy and emits resilience alerts."""

    def __init__(
        self,
        *,
        stale_after_seconds: float = 300.0,
        alert_publisher: AlertPublisher | None = None,
        alert_routing_key: str = "news.alerts",
        service_name: str = "news_summarizer",
    ) -> None:
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")

        self.stale_after_seconds = float(stale_after_seconds)
        self.alert_publisher = alert_publisher
        self.alert_routing_key = alert_routing_key
        self.service_name = service_name

    def evaluate(
        self,
        *,
        summary: NewsSummaryArtifact | None,
        now: datetime | None = None,
    ) -> NewsResilienceDecision:
        now_utc = _to_utc(now)

        if summary is None:
            news_payload = _fallback_payload(reason="missing_summary")
            alert = NewsResilienceAlert(
                event_type="news.resilience.unavailable",
                severity="WARNING",
                reason="missing_summary",
                details={"stale_after_seconds": self.stale_after_seconds},
            )
            return NewsResilienceDecision(
                degraded=True,
                reason="missing_summary",
                news_payload=news_payload,
                alerts=(alert,),
            )

        if summary.summary_text.strip() == "news_unavailable":
            news_payload = _fallback_payload(reason="upstream_unavailable")
            alert = NewsResilienceAlert(
                event_type="news.resilience.unavailable",
                severity="WARNING",
                reason="upstream_unavailable",
                details={"summary_id": summary.summary_id},
            )
            return NewsResilienceDecision(
                degraded=True,
                reason="upstream_unavailable",
                news_payload=news_payload,
                alerts=(alert,),
            )

        generated_at = _parse_iso(summary.generated_at)
        age_seconds = max(0.0, (now_utc - generated_at).total_seconds())
        if age_seconds > self.stale_after_seconds:
            news_payload = _fallback_payload(reason="stale_summary")
            alert = NewsResilienceAlert(
                event_type="news.resilience.stale",
                severity="WARNING",
                reason="stale_summary",
                details={
                    "summary_id": summary.summary_id,
                    "age_seconds": age_seconds,
                    "stale_after_seconds": self.stale_after_seconds,
                },
            )
            return NewsResilienceDecision(
                degraded=True,
                reason="stale_summary",
                news_payload=news_payload,
                alerts=(alert,),
            )

        source_count = len(summary.source_news_ids)
        sentiment = _sentiment_hint(summary.summary_text)
        return NewsResilienceDecision(
            degraded=False,
            reason="ok",
            news_payload={
                "summary": summary.summary_text,
                "sentiment": sentiment,
                "source_count": source_count,
                "is_fallback": False,
                "summary_id": summary.summary_id,
            },
            alerts=(),
        )

    async def publish_alerts(
        self,
        *,
        alerts: tuple[NewsResilienceAlert, ...],
        trace_id: str,
        decision_id: str,
        mode: str,
    ) -> tuple[dict[str, Any], ...]:
        if not alerts or self.alert_publisher is None:
            return ()

        envelopes: list[dict[str, Any]] = []
        for index, alert in enumerate(alerts):
            payload = {
                "severity": alert.severity,
                "reason": alert.reason,
                "details": dict(alert.details),
                "news_payload": _fallback_payload(reason=alert.reason),
            }
            envelope = {
                "trace_id": trace_id,
                "decision_id": decision_id,
                "mode": mode,
                "idempotency_key": f"news.alert:{decision_id}:{index}:{alert.event_type}",
                "event_type": alert.event_type,
                "emitted_at": _utc_now_iso(),
                "payload": payload,
                "service": self.service_name,
            }
            validate_envelope(envelope)
            await self.alert_publisher.publish(routing_key=self.alert_routing_key, message=envelope)
            envelopes.append(envelope)
        return tuple(envelopes)


def _fallback_payload(*, reason: str) -> dict[str, Any]:
    return {
        "summary": "news_unavailable",
        "sentiment": 0.0,
        "source_count": 0,
        "is_fallback": True,
        "reason": reason,
    }


def _sentiment_hint(summary_text: str) -> float:
    lowered = summary_text.lower()
    positive_hits = sum(
        token in lowered for token in ("bull", "strong", "inflow", "approval", "growth")
    )
    negative_hits = sum(token in lowered for token in ("bear", "panic", "hack", "exploit", "drop"))
    total = positive_hits + negative_hits
    if total == 0:
        return 0.0
    return max(-1.0, min(1.0, (positive_hits - negative_hits) / total))


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _to_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
