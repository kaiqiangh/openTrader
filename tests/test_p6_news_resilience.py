from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from services.news_summarizer.resilience import NewsResiliencePolicy
from services.news_summarizer.summarizer_service import NewsSummaryArtifact
from services.shared.runtime.broker import InMemoryTopicBroker


def _summary(*, generated_at: str, text: str = "BTC market context") -> NewsSummaryArtifact:
    return NewsSummaryArtifact(
        summary_id=str(uuid.uuid4()),
        symbol_scope="BTC",
        window_start="2026-02-14T18:00:00Z",
        window_end="2026-02-14T19:00:00Z",
        summary_text=text,
        token_count=len(text.split()),
        generated_at=generated_at,
        source_news_ids=("news-1", "news-2"),
    )


def test_resilience_returns_fallback_and_alert_when_summary_missing() -> None:
    policy = NewsResiliencePolicy(stale_after_seconds=300)

    decision = policy.evaluate(summary=None, now=datetime(2026, 2, 14, 19, 0, tzinfo=timezone.utc))

    assert decision.degraded is True
    assert decision.news_payload["summary"] == "news_unavailable"
    assert decision.news_payload["is_fallback"] is True
    assert len(decision.alerts) == 1
    assert decision.alerts[0].event_type == "news.resilience.unavailable"


def test_resilience_returns_fallback_and_alert_when_summary_is_stale() -> None:
    policy = NewsResiliencePolicy(stale_after_seconds=60)

    decision = policy.evaluate(
        summary=_summary(generated_at="2026-02-14T18:58:00Z"),
        now=datetime(2026, 2, 14, 19, 0, 30, tzinfo=timezone.utc),
    )

    assert decision.degraded is True
    assert decision.reason == "stale_summary"
    assert decision.news_payload["summary"] == "news_unavailable"
    assert decision.alerts[0].severity == "WARNING"


def test_resilience_accepts_fresh_summary_without_alert() -> None:
    policy = NewsResiliencePolicy(stale_after_seconds=120)

    decision = policy.evaluate(
        summary=_summary(generated_at="2026-02-14T18:59:50Z", text="Fresh summary"),
        now=datetime(2026, 2, 14, 19, 0, 10, tzinfo=timezone.utc),
    )

    assert decision.degraded is False
    assert decision.reason == "ok"
    assert decision.news_payload["summary"] == "Fresh summary"
    assert decision.alerts == ()


@pytest.mark.asyncio
async def test_resilience_publishes_alert_envelopes() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    broker.declare_queue("news.alerts")
    broker.bind_queue(routing_key="news.alerts", queue_name="news.alerts")

    policy = NewsResiliencePolicy(
        stale_after_seconds=120, alert_publisher=broker, alert_routing_key="news.alerts"
    )
    decision = policy.evaluate(summary=None, now=datetime(2026, 2, 14, 19, 5, tzinfo=timezone.utc))

    await policy.publish_alerts(
        alerts=decision.alerts,
        trace_id=str(uuid.uuid4()),
        decision_id=str(uuid.uuid4()),
        mode="MOCK",
    )

    consumed = await broker.consume(queue_name="news.alerts", timeout_seconds=0.0)

    assert consumed is not None
    assert consumed["event_type"] == "news.resilience.unavailable"
    assert consumed["payload"]["severity"] == "WARNING"
    assert consumed["payload"]["news_payload"]["summary"] == "news_unavailable"
