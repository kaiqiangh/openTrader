from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Protocol, Sequence
import uuid

from services.market_ingestion.contracts import OrderBookDelta
from services.market_ingestion.kline_validator import KlineBar, KlineReconstructionValidator
from services.shared.contracts.message_envelope import validate_envelope


class CanonicalPublisher(Protocol):
    async def publish(self, *, routing_key: str, message: Mapping[str, Any]) -> None: ...


class CanonicalNormalizationPipeline:
    def __init__(
        self, *, publisher: CanonicalPublisher, service_name: str = "market_ingestion"
    ) -> None:
        self.publisher = publisher
        self.service_name = service_name

    def normalize_order_book_delta(self, delta: OrderBookDelta) -> dict[str, Any]:
        return {
            "exchange": delta.exchange,
            "symbol": delta.symbol,
            "timestamp_ms": delta.timestamp_ms,
            "sequence_start": delta.sequence_start,
            "sequence_end": delta.sequence_end,
            "bids": [{"price": level.price, "amount": level.amount} for level in delta.bids],
            "asks": [{"price": level.price, "amount": level.amount} for level in delta.asks],
        }

    async def publish_order_book_delta(self, delta: OrderBookDelta, *, mode: str) -> dict[str, Any]:
        payload = self.normalize_order_book_delta(delta)
        sequence_marker = delta.sequence_end if delta.sequence_end is not None else "na"
        idempotency_key = (
            f"market.canonical.orderbook_delta:{delta.exchange}:{delta.symbol}:{sequence_marker}"
        )
        envelope = self._build_envelope(
            event_type="market.canonical.orderbook_delta",
            mode=mode,
            payload=payload,
            idempotency_key=idempotency_key,
        )
        await self.publisher.publish(routing_key="market.canonical", message=envelope)
        return envelope

    async def publish_kline_validation(
        self,
        *,
        exchange: str,
        symbol: str,
        interval_ms: int,
        bars: Sequence[KlineBar],
        mode: str,
    ) -> dict[str, Any]:
        validator = KlineReconstructionValidator(interval_ms=interval_ms)
        validation = validator.validate(bars)
        payload = {
            "exchange": exchange,
            "symbol": symbol,
            "interval_ms": interval_ms,
            "bar_count": len(bars),
            "validation": {
                "is_valid": validation.is_valid,
                "missing_open_times": list(validation.missing_open_times),
                "errors": list(validation.errors),
            },
        }

        first_open = bars[0].open_time_ms if bars else "na"
        last_open = bars[-1].open_time_ms if bars else "na"
        idempotency_key = (
            f"market.canonical.kline_validation:{exchange}:{symbol}:{first_open}:{last_open}"
        )
        envelope = self._build_envelope(
            event_type="market.canonical.kline_validation",
            mode=mode,
            payload=payload,
            idempotency_key=idempotency_key,
        )
        await self.publisher.publish(routing_key="market.canonical", message=envelope)
        return envelope

    def _build_envelope(
        self,
        *,
        event_type: str,
        mode: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        envelope = {
            "trace_id": str(uuid.uuid4()),
            "decision_id": str(uuid.uuid4()),
            "mode": mode,
            "idempotency_key": idempotency_key,
            "event_type": event_type,
            "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "payload": dict(payload),
            "service": self.service_name,
        }
        validate_envelope(envelope)
        return envelope
