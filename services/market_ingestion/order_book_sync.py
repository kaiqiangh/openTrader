from __future__ import annotations

from services.market_ingestion.contracts import OrderBookDelta, OrderBookSnapshot


class OrderBookSyncError(RuntimeError):
    """Base sync engine failure."""


class OrderBookNotInitializedError(OrderBookSyncError):
    """Raised when applying a delta before snapshot bootstrap."""


class OrderBookSequenceGapError(OrderBookSyncError):
    """Raised when a delta skips the expected next sequence number."""


class OrderBookSyncEngine:
    def __init__(self, *, exchange: str, symbol: str) -> None:
        self.exchange = exchange
        self.symbol = symbol
        self._sequence: int | None = None
        self._bids: dict[float, float] = {}
        self._asks: dict[float, float] = {}
        self._initialized = False

    def load_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        self._validate_scope(snapshot.exchange, snapshot.symbol)
        self._bids = {level.price: level.amount for level in snapshot.bids if level.amount > 0}
        self._asks = {level.price: level.amount for level in snapshot.asks if level.amount > 0}
        self._sequence = snapshot.sequence
        self._initialized = True

    def apply_delta(self, delta: OrderBookDelta) -> bool:
        if not self._initialized:
            raise OrderBookNotInitializedError("Call load_snapshot before apply_delta")

        self._validate_scope(delta.exchange, delta.symbol)
        if self._sequence is not None and delta.sequence_start is not None and delta.sequence_end is not None:
            expected = self._sequence + 1
            if delta.sequence_end < expected:
                return False
            if delta.sequence_start > expected:
                raise OrderBookSequenceGapError(
                    f"Expected sequence {expected} but received {delta.sequence_start}"
                )
            self._sequence = delta.sequence_end
        elif delta.sequence_end is not None:
            self._sequence = delta.sequence_end

        self._apply_side_updates(self._bids, delta.bids)
        self._apply_side_updates(self._asks, delta.asks)
        return True

    def materialize_snapshot(self, *, depth: int = 20) -> dict:
        bid_levels = sorted(self._bids.items(), key=lambda item: item[0], reverse=True)[:depth]
        ask_levels = sorted(self._asks.items(), key=lambda item: item[0])[:depth]
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "sequence": self._sequence,
            "bids": [{"price": price, "amount": amount} for price, amount in bid_levels],
            "asks": [{"price": price, "amount": amount} for price, amount in ask_levels],
        }

    def _validate_scope(self, exchange: str, symbol: str) -> None:
        if exchange != self.exchange or symbol != self.symbol:
            raise OrderBookSyncError("Delta/snapshot scope does not match engine scope")

    @staticmethod
    def _apply_side_updates(book: dict[float, float], updates) -> None:
        for level in updates:
            if level.amount <= 0:
                book.pop(level.price, None)
            else:
                book[level.price] = level.amount
