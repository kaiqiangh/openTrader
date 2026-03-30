from __future__ import annotations

import time

import pytest

from services.market_ingestion.canonical_pipeline import CanonicalNormalizationPipeline
from services.market_ingestion.exchange_adapter import CCXTIngestionAdapter
from services.shared.runtime.broker import InMemoryTopicBroker
from services.workers.runtime_pipeline import MarketIngestionRuntimeWorker


class _ScriptedRestClient:
    def __init__(self, *, snapshots: tuple[dict[str, object], ...]) -> None:
        self.snapshots = list(snapshots)
        self.fetch_calls = 0

    async def fetch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, object]:
        _ = symbol, limit
        self.fetch_calls += 1
        if not self.snapshots:
            raise AssertionError("no scripted snapshot remaining")
        return dict(self.snapshots.pop(0))


class _ScriptedWsClient:
    def __init__(self, *, deltas: tuple[dict[str, object], ...]) -> None:
        self.deltas = list(deltas)
        self.watch_calls = 0

    async def watch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, object]:
        _ = symbol, limit
        self.watch_calls += 1
        if not self.deltas:
            raise RuntimeError("websocket stream unavailable")
        next_delta = self.deltas.pop(0)
        if isinstance(next_delta, Exception):
            raise next_delta
        return dict(next_delta)


def _snapshot(*, sequence: int, bid: float, ask: float) -> dict[str, object]:
    return {
        "nonce": sequence,
        "timestamp": 1739535600000 + sequence,
        "bids": [[bid, 5.0], [bid - 1.0, 2.0]],
        "asks": [[ask, 3.0], [ask + 1.0, 1.0]],
    }


def _delta(*, start: int, end: int, bid: float, ask: float) -> dict[str, object]:
    return {
        "U": start,
        "u": end,
        "timestamp": 1739535600000 + end,
        "bids": [[bid, 4.0]],
        "asks": [[ask, 2.0]],
    }


@pytest.mark.asyncio
async def test_phase3_websocket_gap_resyncs_to_rest_snapshot() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    rest = _ScriptedRestClient(
        snapshots=(
            _snapshot(sequence=100, bid=42000.0, ask=42001.0),  # bootstrap
            _snapshot(sequence=110, bid=42010.0, ask=42011.0),  # resync fallback
        )
    )
    ws = _ScriptedWsClient(
        deltas=(
            _delta(start=120, end=121, bid=42012.0, ask=42013.0),  # intentional sequence gap
        )
    )
    worker = MarketIngestionRuntimeWorker(
        adapter=CCXTIngestionAdapter(
            exchange="binance", rest_client=rest, ws_client=ws, delta_source="websocket"
        ),
        pipeline=CanonicalNormalizationPipeline(publisher=broker),
        symbol="BTC/USDT",
        mode="MOCK",
        depth=20,
        ws_stale_after_seconds=15.0,
        ws_probe_interval_seconds=0.1,
    )

    envelope = await worker.run_once()

    payload = envelope["payload"]
    assert payload["sequence_start"] == 110
    assert payload["sequence_end"] == 110
    assert payload["bids"][0]["price"] == 42010.0
    assert rest.fetch_calls == 2
    assert ws.watch_calls == 1


@pytest.mark.asyncio
async def test_phase3_websocket_stale_stream_cutover_uses_rest_snapshot() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    rest = _ScriptedRestClient(
        snapshots=(
            _snapshot(sequence=100, bid=42000.0, ask=42001.0),  # bootstrap
            _snapshot(sequence=101, bid=42001.0, ask=42002.0),  # stale cutover fallback
        )
    )
    ws = _ScriptedWsClient(deltas=(_delta(start=101, end=101, bid=42000.5, ask=42001.5),))
    worker = MarketIngestionRuntimeWorker(
        adapter=CCXTIngestionAdapter(
            exchange="binance", rest_client=rest, ws_client=ws, delta_source="websocket"
        ),
        pipeline=CanonicalNormalizationPipeline(publisher=broker),
        symbol="BTC/USDT",
        mode="MOCK",
        depth=20,
        ws_stale_after_seconds=0.01,
        ws_probe_interval_seconds=60.0,
    )

    _ = await worker.run_once()
    assert ws.watch_calls == 1

    assert worker._resilience is not None
    worker._resilience.mark_heartbeat(now_seconds=0.0)
    worker._next_ws_probe_monotonic = time.monotonic() + 60.0

    envelope = await worker.run_once()

    payload = envelope["payload"]
    assert payload["sequence_start"] == 101
    assert payload["sequence_end"] == 101
    assert payload["bids"][0]["price"] == 42001.0
    assert rest.fetch_calls == 2
    assert ws.watch_calls == 1


@pytest.mark.asyncio
async def test_phase3_websocket_error_falls_back_to_rest_snapshot() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    rest = _ScriptedRestClient(
        snapshots=(
            _snapshot(sequence=100, bid=42000.0, ask=42001.0),  # bootstrap
            _snapshot(sequence=108, bid=42008.0, ask=42009.0),  # websocket error fallback
        )
    )
    ws = _ScriptedWsClient(deltas=(RuntimeError("socket disconnected"),))
    worker = MarketIngestionRuntimeWorker(
        adapter=CCXTIngestionAdapter(
            exchange="binance", rest_client=rest, ws_client=ws, delta_source="websocket"
        ),
        pipeline=CanonicalNormalizationPipeline(publisher=broker),
        symbol="BTC/USDT",
        mode="MOCK",
        depth=20,
        ws_stale_after_seconds=15.0,
        ws_probe_interval_seconds=0.1,
    )

    envelope = await worker.run_once()

    payload = envelope["payload"]
    assert payload["sequence_start"] == 108
    assert payload["sequence_end"] == 108
    assert payload["asks"][0]["price"] == 42009.0
    assert rest.fetch_calls == 2
    assert ws.watch_calls == 1
