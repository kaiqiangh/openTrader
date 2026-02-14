from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class GapDetectionResult:
    has_gap: bool
    expected_sequence: int | None
    received_sequence_start: int | None
    received_sequence_end: int | None
    gap_size: int
    action: str


class GapDetectionModule:
    def evaluate(
        self,
        *,
        current_sequence: int | None,
        incoming_start: int | None,
        incoming_end: int | None,
    ) -> GapDetectionResult:
        if current_sequence is None or incoming_start is None or incoming_end is None:
            return GapDetectionResult(
                has_gap=False,
                expected_sequence=None,
                received_sequence_start=incoming_start,
                received_sequence_end=incoming_end,
                gap_size=0,
                action="accept",
            )

        expected_sequence = current_sequence + 1
        if incoming_end < expected_sequence:
            return GapDetectionResult(
                has_gap=False,
                expected_sequence=expected_sequence,
                received_sequence_start=incoming_start,
                received_sequence_end=incoming_end,
                gap_size=0,
                action="ignore_stale",
            )

        if incoming_start > expected_sequence:
            return GapDetectionResult(
                has_gap=True,
                expected_sequence=expected_sequence,
                received_sequence_start=incoming_start,
                received_sequence_end=incoming_end,
                gap_size=incoming_start - expected_sequence,
                action="resync",
            )

        return GapDetectionResult(
            has_gap=False,
            expected_sequence=expected_sequence,
            received_sequence_start=incoming_start,
            received_sequence_end=incoming_end,
            gap_size=0,
            action="accept",
        )

    def build_resync_request(
        self,
        *,
        exchange: str,
        symbol: str,
        result: GapDetectionResult,
        reason: str,
    ) -> dict[str, object]:
        return {
            "exchange": exchange,
            "symbol": symbol,
            "reason": reason,
            "expected_sequence": result.expected_sequence,
            "received_sequence_start": result.received_sequence_start,
            "received_sequence_end": result.received_sequence_end,
            "gap_size": result.gap_size,
            "requested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
