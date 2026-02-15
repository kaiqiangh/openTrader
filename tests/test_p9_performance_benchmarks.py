from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter, time
import math
import uuid

import pytest

from services.market_ingestion.canonical_pipeline import CanonicalNormalizationPipeline
from services.market_ingestion.exchange_adapter import CCXTIngestionAdapter
from services.shared.runtime.broker import InMemoryTopicBroker
from services.simulation_execution.worker import SimulationExecutionWorker
from services.workers.runtime_pipeline import MarketIngestionRuntimeWorker


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * (percentile / 100.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(ordered[lower])
    lower_value = ordered[lower]
    upper_value = ordered[upper]
    weight = rank - lower
    return float(lower_value + (upper_value - lower_value) * weight)


def _build_mock_execution_intent(index: int) -> dict[str, object]:
    return {
        "trace_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"p9-dispatch-trace:{index}")),
        "decision_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"p9-dispatch-decision:{index}")),
        "mode": "MOCK",
        "idempotency_key": f"execution.intent:mock:p9-bench:{index}",
        "event_type": "execution.intent.created",
        "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "payload": {
            "strategy_id": "latency-bench",
            "symbol": "BTC/USDT",
            "action": "BUY",
            "quantity": 0.01,
            "market_context": {"mid_price": 42_000.0},
        },
        "service": "p9_perf_bench",
    }


def _iso_to_epoch_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


class _ClockedRestClient:
    def __init__(self) -> None:
        self.sequence = 1_000

    async def fetch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, object]:
        _ = limit
        assert symbol == "BTC/USDT"
        now_ms = int(time() * 1000)
        return {
            "nonce": self.sequence,
            "timestamp": now_ms,
            "bids": [[42000.0, 5.0], [41999.0, 1.0]],
            "asks": [[42001.0, 3.0], [42002.0, 1.0]],
        }


class _ClockedWsClient:
    def __init__(self, rest_client: _ClockedRestClient) -> None:
        self.sequence = rest_client.sequence

    async def watch_order_book(self, symbol: str, limit: int | None = None) -> dict[str, object]:
        _ = limit
        assert symbol == "BTC/USDT"
        self.sequence += 1
        now_ms = int(time() * 1000)
        return {
            "U": self.sequence,
            "u": self.sequence,
            "timestamp": now_ms,
            "bids": [[42000.0, 5.5], [41999.0, 1.0]],
            "asks": [[42001.0, 2.5], [42002.0, 0.8]],
        }


@pytest.mark.asyncio
async def test_p9_dispatch_latency_p95_stays_within_budget() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    worker = SimulationExecutionWorker(broker=broker)
    sample_size = 180

    for idx in range(sample_size):
        await broker.publish(
            routing_key="execution.intent.mock",
            message=_build_mock_execution_intent(idx),
        )

    latencies_ms: list[float] = []
    for _ in range(sample_size):
        started = perf_counter()
        result = await worker.run_once(timeout_seconds=0.0)
        latency_ms = (perf_counter() - started) * 1000.0
        latencies_ms.append(latency_ms)
        assert result is not None
        assert result.status == "FILLED"

    p95_latency_ms = _percentile(latencies_ms, 95.0)
    assert p95_latency_ms < 150.0


@pytest.mark.asyncio
async def test_p9_queue_throughput_exceeds_minimum() -> None:
    broker = InMemoryTopicBroker()
    broker.declare_queue("p9.bench.queue")
    sample_size = 1_200

    started = perf_counter()
    for idx in range(sample_size):
        await broker.publish(routing_key="p9.bench.queue", message={"index": idx})
    for _ in range(sample_size):
        consumed = await broker.consume(queue_name="p9.bench.queue", timeout_seconds=0.0)
        assert consumed is not None
    elapsed_seconds = max(perf_counter() - started, 1e-6)

    throughput = sample_size / elapsed_seconds
    assert throughput > 300.0


@pytest.mark.asyncio
async def test_p9_ingestion_lag_p95_stays_within_budget() -> None:
    broker = InMemoryTopicBroker.from_topology_file("config/rabbitmq/topology.json")
    rest = _ClockedRestClient()
    ws = _ClockedWsClient(rest)
    worker = MarketIngestionRuntimeWorker(
        adapter=CCXTIngestionAdapter(exchange="binance", rest_client=rest, ws_client=ws),
        pipeline=CanonicalNormalizationPipeline(publisher=broker),
        symbol="BTC/USDT",
        mode="MOCK",
        depth=20,
    )

    lags_ms: list[float] = []
    for _ in range(60):
        envelope = await worker.run_once()
        emitted_at = _iso_to_epoch_ms(str(envelope["emitted_at"]))
        payload = envelope["payload"]
        assert isinstance(payload, dict)
        source_timestamp = int(payload["timestamp_ms"])
        lag = max(0, emitted_at - source_timestamp)
        lags_ms.append(float(lag))

    assert _percentile(lags_ms, 95.0) < 1_000.0
