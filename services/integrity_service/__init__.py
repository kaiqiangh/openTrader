"""Integrity service boundary for market data quality and recovery rules.

This package is the canonical bounded context for integrity logic. During the
Phase 10 transition, core implementations are re-exported from
``services.market_ingestion`` to avoid breaking existing imports while moving
toward dedicated integrity workers.
"""

from services.integrity_service.gap_detection import GapDetectionModule, GapDetectionResult
from services.integrity_service.kline_validator import (
    KlineBar,
    KlineReconstructionValidator,
    KlineValidationResult,
)
from services.integrity_service.order_book_sync import (
    OrderBookDelta,
    OrderBookLevel,
    OrderBookNotInitializedError,
    OrderBookSequenceGapError,
    OrderBookSnapshot,
    OrderBookSyncError,
    OrderBookSyncEngine,
)

__all__ = [
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
    "OrderBookSyncError",
    "OrderBookSyncEngine",
]
