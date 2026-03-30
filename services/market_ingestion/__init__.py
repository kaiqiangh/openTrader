"""Market ingestion foundation components."""

from services.market_ingestion.binance_http_adapter import BinanceHTTPOrderBookClient
from services.market_ingestion.bitget_http_adapter import BitgetHTTPOrderBookClient
from services.market_ingestion.canonical_pipeline import (
    CanonicalNormalizationPipeline,
    CanonicalPublisher,
)
from services.market_ingestion.connection_resilience import (
    BackoffConfig,
    ConnectionResilienceManager,
)
from services.market_ingestion.contracts import OrderBookDelta, OrderBookLevel, OrderBookSnapshot
from services.market_ingestion.exchange_adapter import (
    AdapterConfigurationError,
    AdapterPayloadError,
    CCXTIngestionAdapter,
    RestOrderBookClient,
    WsOrderBookClient,
)
from services.market_ingestion.gap_detection import GapDetectionModule, GapDetectionResult
from services.market_ingestion.integration_harness import (
    IngestionIntegrationHarness,
    ReplayRunResult,
)
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
from services.market_ingestion.persistence_writers import (
    TimescalePersistenceWriters,
    TimeseriesStore,
)
from services.market_ingestion.pipeline_metrics import MarketPipelineMetrics

__all__ = [
    "AdapterConfigurationError",
    "AdapterPayloadError",
    "BackoffConfig",
    "BinanceHTTPOrderBookClient",
    "BitgetHTTPOrderBookClient",
    "CanonicalNormalizationPipeline",
    "CanonicalPublisher",
    "CCXTIngestionAdapter",
    "ConnectionResilienceManager",
    "GapDetectionModule",
    "GapDetectionResult",
    "KlineBar",
    "KlineReconstructionValidator",
    "KlineValidationResult",
    "MarketPipelineMetrics",
    "OrderBookDelta",
    "OrderBookLevel",
    "OrderBookNotInitializedError",
    "OrderBookSequenceGapError",
    "OrderBookSnapshot",
    "OrderBookSyncEngine",
    "OrderBookSyncError",
    "ReplayRunResult",
    "RestOrderBookClient",
    "TimescalePersistenceWriters",
    "TimeseriesStore",
    "WsOrderBookClient",
    "IngestionIntegrationHarness",
]
