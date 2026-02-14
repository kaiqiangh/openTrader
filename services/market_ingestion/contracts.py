from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    price: float
    amount: float


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    exchange: str
    symbol: str
    sequence: int | None
    timestamp_ms: int | None
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]


@dataclass(frozen=True, slots=True)
class OrderBookDelta:
    exchange: str
    symbol: str
    sequence_start: int | None
    sequence_end: int | None
    timestamp_ms: int | None
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]


def parse_levels(
    levels: Iterable[Sequence[float | int | str]],
    *,
    side: str,
    allow_zero: bool,
) -> tuple[OrderBookLevel, ...]:
    normalized: list[OrderBookLevel] = []
    for level in levels:
        if len(level) < 2:
            continue
        price = float(level[0])
        amount = float(level[1])
        if amount < 0:
            continue
        if amount == 0 and not allow_zero:
            continue
        normalized.append(OrderBookLevel(price=price, amount=amount))

    reverse = side == "bid"
    normalized.sort(key=lambda item: item.price, reverse=reverse)
    return tuple(normalized)
