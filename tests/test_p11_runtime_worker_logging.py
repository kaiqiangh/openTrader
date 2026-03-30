from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from services.workers import main as runtime_main
from services.workers.main import RuntimeWorkerBuildResult, RuntimeWorkerSettings, run_worker_loop


@dataclass
class _SequenceWorker:
    responses: list[bool]
    error_on_index: int | None = None
    calls: int = 0

    async def run_once(self, *, timeout_seconds: float) -> bool:
        _ = timeout_seconds
        if self.error_on_index is not None and self.calls == self.error_on_index:
            self.calls += 1
            raise RuntimeError("boom")
        if self.calls >= len(self.responses):
            self.calls += 1
            return False
        result = bool(self.responses[self.calls])
        self.calls += 1
        return result


@dataclass
class _NoopBroker:
    bootstrapped: bool = False

    async def bootstrap_topology(self) -> None:
        self.bootstrapped = True


class _CapturedLogger:
    records: list[dict[str, Any]] = []

    def __init__(self, *, service: str) -> None:
        self.service = service

    def info(
        self, *, event: str, context: dict[str, Any] | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        payload = {"level": "INFO", "event": event, "context": dict(context or {}), **kwargs}
        self.__class__.records.append(payload)
        return payload

    def error(
        self, *, event: str, context: dict[str, Any] | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        payload = {"level": "ERROR", "event": event, "context": dict(context or {}), **kwargs}
        self.__class__.records.append(payload)
        return payload


@dataclass
class _ActivityWorker:
    calls: int = 0

    async def run_once(self, *, timeout_seconds: float) -> bool:
        _ = timeout_seconds
        self.calls += 1
        return True

    def activity_snapshot(self) -> dict[str, Any]:
        return {
            "trace_id": "trace-123",
            "decision_id": "decision-456",
            "mode": "MOCK",
            "status": "RISK_APPROVED",
            "event": "agent.decision.completed",
        }


def _settings(*, once: bool, bootstrap_topology: bool = False) -> RuntimeWorkerSettings:
    return RuntimeWorkerSettings(
        worker="market",
        broker_backend="inmemory",
        topology_path="config/rabbitmq/topology.json",
        mode="MOCK",
        symbol="BTC/USDT",
        strategy_id="default-strategy",
        once=once,
        validate_only=False,
        max_idle_cycles=1,
        poll_timeout_seconds=0.0,
        idle_sleep_seconds=0.0,
        bootstrap_topology=bootstrap_topology,
        portfolio_base_balance_usd=100000.0,
        require_database=False,
    )


@pytest.mark.asyncio
async def test_worker_loop_logs_idle_heartbeat_and_exit_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _CapturedLogger.records = []
    monkeypatch.setattr(runtime_main, "StructuredLogger", _CapturedLogger)
    monkeypatch.setenv("RUNTIME_WORKER_IDLE_HEARTBEAT_CYCLES", "1")
    worker = _SequenceWorker(responses=[False])
    build = RuntimeWorkerBuildResult(worker=worker, broker=object())

    code = await run_worker_loop(settings=_settings(once=True), build=build)

    assert code == 0
    events = [record["event"] for record in _CapturedLogger.records]
    assert "runtime.worker.started" in events
    assert "runtime.worker.idle_heartbeat" in events
    assert "runtime.worker.exited" in events
    exit_record = next(
        record for record in _CapturedLogger.records if record["event"] == "runtime.worker.exited"
    )
    assert exit_record["context"]["reason"] == "once_no_work"


@pytest.mark.asyncio
async def test_worker_loop_logs_success_cycle_and_exit_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _CapturedLogger.records = []
    monkeypatch.setattr(runtime_main, "StructuredLogger", _CapturedLogger)
    worker = _SequenceWorker(responses=[True])
    build = RuntimeWorkerBuildResult(worker=worker, broker=object())

    code = await run_worker_loop(settings=_settings(once=True), build=build)

    assert code == 0
    events = [record["event"] for record in _CapturedLogger.records]
    assert "runtime.worker.cycle_succeeded" in events
    exit_record = next(
        record for record in _CapturedLogger.records if record["event"] == "runtime.worker.exited"
    )
    assert exit_record["context"]["reason"] == "once_cycle_completed"


@pytest.mark.asyncio
async def test_worker_loop_logs_failure_and_exit_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    _CapturedLogger.records = []
    monkeypatch.setattr(runtime_main, "StructuredLogger", _CapturedLogger)
    worker = _SequenceWorker(responses=[], error_on_index=0)
    build = RuntimeWorkerBuildResult(worker=worker, broker=object())

    code = await run_worker_loop(settings=_settings(once=True), build=build)

    assert code == 1
    events = [record["event"] for record in _CapturedLogger.records]
    assert "runtime.worker.cycle_failed" in events
    exit_record = next(
        record for record in _CapturedLogger.records if record["event"] == "runtime.worker.exited"
    )
    assert exit_record["context"]["reason"] == "once_cycle_failed"


@pytest.mark.asyncio
async def test_worker_loop_logs_topology_bootstrap_event(monkeypatch: pytest.MonkeyPatch) -> None:
    _CapturedLogger.records = []
    monkeypatch.setattr(runtime_main, "StructuredLogger", _CapturedLogger)
    broker = _NoopBroker()
    worker = _SequenceWorker(responses=[False])
    build = RuntimeWorkerBuildResult(worker=worker, broker=broker)

    code = await run_worker_loop(
        settings=_settings(once=True, bootstrap_topology=True), build=build
    )

    assert code == 0
    assert broker.bootstrapped is True
    events = [record["event"] for record in _CapturedLogger.records]
    assert "runtime.worker.topology_bootstrapped" in events


@pytest.mark.asyncio
async def test_worker_loop_logs_activity_snapshot_and_correlation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _CapturedLogger.records = []
    monkeypatch.setattr(runtime_main, "StructuredLogger", _CapturedLogger)
    worker = _ActivityWorker()
    build = RuntimeWorkerBuildResult(worker=worker, broker=object())

    code = await run_worker_loop(settings=_settings(once=True), build=build)

    assert code == 0
    success_record = next(
        record
        for record in _CapturedLogger.records
        if record["event"] == "runtime.worker.cycle_succeeded"
    )
    assert success_record["trace_id"] == "trace-123"
    assert success_record["decision_id"] == "decision-456"
    assert success_record["mode"] == "MOCK"
    assert success_record["context"]["activity"]["status"] == "RISK_APPROVED"
