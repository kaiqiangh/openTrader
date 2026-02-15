from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from services.market_ingestion.contracts import OrderBookDelta, OrderBookSnapshot, parse_levels


class AdapterPayloadError(ValueError):
    """Raised when exchange payload does not satisfy adapter assumptions."""


class AdapterConfigurationError(ValueError):
    """Raised when exchange adapter configuration is invalid."""


class RestOrderBookClient(Protocol):
    async def fetch_order_book(self, symbol: str, limit: int | None = None) -> Mapping[str, Any]: ...


class WsOrderBookClient(Protocol):
    async def watch_order_book(self, symbol: str, limit: int | None = None) -> Mapping[str, Any]: ...


@dataclass(slots=True)
class CCXTIngestionAdapter:
    exchange: str
    rest_client: RestOrderBookClient
    ws_client: WsOrderBookClient
    delta_source: str = "websocket"

    async def bootstrap_snapshot(self, symbol: str, limit: int = 200) -> OrderBookSnapshot:
        raw = await self.rest_client.fetch_order_book(symbol, limit=limit)
        return self._normalize_snapshot(symbol=symbol, raw=raw)

    async def poll_delta(self, symbol: str, limit: int = 200) -> OrderBookDelta:
        source = _normalize_delta_source(self.delta_source)
        if source == "rest":
            raw = await self.rest_client.fetch_order_book(symbol, limit=limit)
        else:
            raw = await self.ws_client.watch_order_book(symbol, limit=limit)
        return self._normalize_delta(symbol=symbol, raw=raw)

    def _normalize_snapshot(self, *, symbol: str, raw: Mapping[str, Any]) -> OrderBookSnapshot:
        bids = raw.get("bids")
        asks = raw.get("asks")
        if not isinstance(bids, list) or not isinstance(asks, list):
            raise AdapterPayloadError("Snapshot payload must contain list bids and asks")

        sequence = _parse_optional_int(raw.get("nonce") or raw.get("sequence"))
        timestamp_ms = _parse_optional_int(raw.get("timestamp"))
        return OrderBookSnapshot(
            exchange=self.exchange,
            symbol=symbol,
            sequence=sequence,
            timestamp_ms=timestamp_ms,
            bids=parse_levels(bids, side="bid", allow_zero=False),
            asks=parse_levels(asks, side="ask", allow_zero=False),
        )

    def _normalize_delta(self, *, symbol: str, raw: Mapping[str, Any]) -> OrderBookDelta:
        bids = raw.get("bids")
        asks = raw.get("asks")
        if not isinstance(bids, list) or not isinstance(asks, list):
            raise AdapterPayloadError("Delta payload must contain list bids and asks")

        sequence_start = _parse_optional_int(raw.get("U") or raw.get("sequence_start"))
        sequence_end = _parse_optional_int(raw.get("u") or raw.get("sequence_end"))
        if sequence_start is None and sequence_end is None:
            nonce = _parse_optional_int(raw.get("nonce") or raw.get("sequence"))
            sequence_start = nonce
            sequence_end = nonce

        return OrderBookDelta(
            exchange=self.exchange,
            symbol=symbol,
            sequence_start=sequence_start,
            sequence_end=sequence_end,
            timestamp_ms=_parse_optional_int(raw.get("timestamp")),
            bids=parse_levels(bids, side="bid", allow_zero=True),
            asks=parse_levels(asks, side="ask", allow_zero=True),
        )


def _parse_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive fallback
        return None


def _normalize_delta_source(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"websocket", "ws"}:
        return "websocket"
    if normalized in {"rest", "restful", "http"}:
        return "rest"
    raise AdapterConfigurationError("delta_source must be 'websocket' or 'rest'")
