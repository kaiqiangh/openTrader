from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class KlineBar:
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class KlineValidationResult:
    is_valid: bool
    missing_open_times: tuple[int, ...]
    errors: tuple[str, ...]


class KlineReconstructionValidator:
    def __init__(self, *, interval_ms: int) -> None:
        self.interval_ms = interval_ms

    def validate(self, bars: Sequence[KlineBar]) -> KlineValidationResult:
        if not bars:
            return KlineValidationResult(is_valid=True, missing_open_times=(), errors=())

        errors: list[str] = []
        missing_open_times: list[int] = []

        for index in range(1, len(bars)):
            if bars[index].open_time_ms <= bars[index - 1].open_time_ms:
                errors.append("Kline open times must be strictly monotonic increasing")
                break

        for bar in bars:
            max_oc = max(bar.open, bar.close)
            min_oc = min(bar.open, bar.close)
            if bar.high < max_oc or bar.low > min_oc or bar.low > bar.high:
                errors.append(f"Kline high/low consistency violated at {bar.open_time_ms}")
            if bar.volume < 0:
                errors.append(f"Kline volume must be non-negative at {bar.open_time_ms}")

        sorted_bars = sorted(bars, key=lambda item: item.open_time_ms)
        for index in range(1, len(sorted_bars)):
            prev_open = sorted_bars[index - 1].open_time_ms
            curr_open = sorted_bars[index].open_time_ms
            gap = curr_open - prev_open
            if gap <= 0:
                continue
            if gap % self.interval_ms != 0:
                errors.append(f"Kline interval mismatch between {prev_open} and {curr_open}")
            if gap > self.interval_ms:
                missing_open_times.extend(
                    list(range(prev_open + self.interval_ms, curr_open, self.interval_ms))
                )

        is_valid = not errors and not missing_open_times
        return KlineValidationResult(
            is_valid=is_valid,
            missing_open_times=tuple(missing_open_times),
            errors=tuple(errors),
        )
