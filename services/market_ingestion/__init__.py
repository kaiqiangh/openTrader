"""Market ingestion foundation components."""

from services.market_ingestion.connection_resilience import BackoffConfig, ConnectionResilienceManager
from services.market_ingestion.contracts import OrderBookDelta, OrderBookLevel, OrderBookSnapshot
from services.market_ingestion.exchange_adapter import (
    AdapterPayloadError,
    CCXTIngestionAdapter,
    RestOrderBookClient,
    WsOrderBookClient,
)
from services.market_ingestion.order_book_sync import (
    OrderBookNotInitializedError,
    OrderBookSequenceGapError,
    OrderBookSyncEngine,
    OrderBookSyncError,
)

__all__ = [
    "AdapterPayloadError",
    "BackoffConfig",
    "CCXTIngestionAdapter",
    "ConnectionResilienceManager",
    "OrderBookDelta",
    "OrderBookLevel",
    "OrderBookNotInitializedError",
    "OrderBookSequenceGapError",
    "OrderBookSnapshot",
    "OrderBookSyncEngine",
    "OrderBookSyncError",
    "RestOrderBookClient",
    "WsOrderBookClient",
]
