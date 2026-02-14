"""Market ingestion foundation components."""

from services.market_ingestion.canonical_pipeline import CanonicalNormalizationPipeline, CanonicalPublisher
from services.market_ingestion.connection_resilience import BackoffConfig, ConnectionResilienceManager
from services.market_ingestion.contracts import OrderBookDelta, OrderBookLevel, OrderBookSnapshot
from services.market_ingestion.exchange_adapter import (
    AdapterPayloadError,
    CCXTIngestionAdapter,
    RestOrderBookClient,
    WsOrderBookClient,
)
from services.market_ingestion.gap_detection import GapDetectionModule, GapDetectionResult
from services.market_ingestion.kline_validator import (
    KlineBar,
    KlineReconstructionValidator,
    KlineValidationResult,
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
    "CanonicalNormalizationPipeline",
    "CanonicalPublisher",
    "CCXTIngestionAdapter",
    "ConnectionResilienceManager",
    "GapDetectionModule",
    "GapDetectionResult",
    "KlineBar",
    "KlineReconstructionValidator",
    "KlineValidationResult",
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
