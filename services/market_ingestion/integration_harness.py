from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Sequence
import json

from services.market_ingestion.canonical_pipeline import CanonicalNormalizationPipeline
from services.market_ingestion.contracts import OrderBookDelta


class _CapturePublisher:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def publish(self, *, routing_key: str, message: dict[str, Any]) -> None:
        self.messages.append({"routing_key": routing_key, "message": message})


@dataclass(frozen=True, slots=True)
class ReplayRunResult:
    messages: tuple[dict[str, Any], ...]
    stable_digest: str


class IngestionIntegrationHarness:
    async def replay_orderbook_fixture(
        self,
        fixture: Sequence[OrderBookDelta],
        *,
        mode: str,
    ) -> ReplayRunResult:
        publisher = _CapturePublisher()
        pipeline = CanonicalNormalizationPipeline(publisher=publisher)
        for delta in fixture:
            await pipeline.publish_order_book_delta(delta, mode=mode)

        messages = tuple(publisher.messages)
        digest = self._stable_digest(messages)
        return ReplayRunResult(messages=messages, stable_digest=digest)

    async def verify_deterministic_orderbook_replay(
        self,
        fixture: Sequence[OrderBookDelta],
        *,
        mode: str,
    ) -> bool:
        first = await self.replay_orderbook_fixture(fixture, mode=mode)
        second = await self.replay_orderbook_fixture(fixture, mode=mode)
        return first.stable_digest == second.stable_digest

    def _stable_digest(self, messages: Sequence[dict[str, Any]]) -> str:
        digest_parts: list[dict[str, Any]] = []
        for item in messages:
            envelope = item["message"]
            digest_parts.append(
                {
                    "routing_key": item["routing_key"],
                    "event_type": envelope["event_type"],
                    "mode": envelope["mode"],
                    "idempotency_key": envelope["idempotency_key"],
                    "payload": envelope["payload"],
                }
            )
        blob = json.dumps(digest_parts, sort_keys=True, separators=(",", ":"))
        return sha256(blob.encode("utf-8")).hexdigest()
