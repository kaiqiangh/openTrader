from __future__ import annotations

from asyncio import Queue, QueueEmpty, TimeoutError, wait_for
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json


class BrokerConfigurationError(ValueError):
    """Raised when broker topology or queue operations are invalid."""


@dataclass(frozen=True, slots=True)
class PublishedMessage:
    queue: str
    routing_key: str
    message: dict[str, Any]


class InMemoryTopicBroker:
    """In-process topic broker compatible with publisher protocols in this repo."""

    def __init__(self) -> None:
        self._queues: dict[str, Queue[dict[str, Any]]] = {}
        self._bindings: dict[str, set[str]] = defaultdict(set)

    @classmethod
    def from_topology_file(cls, path: str | Path) -> InMemoryTopicBroker:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        broker = cls()
        for queue in payload.get("queues", []):
            if isinstance(queue, dict) and isinstance(queue.get("name"), str):
                broker.declare_queue(str(queue["name"]))

        for binding in payload.get("bindings", []):
            if not isinstance(binding, dict):
                continue
            queue_name = binding.get("queue")
            routing_key = binding.get("routing_key")
            if isinstance(queue_name, str) and isinstance(routing_key, str):
                broker.bind_queue(routing_key=routing_key, queue_name=queue_name)
        return broker

    def declare_queue(self, queue_name: str) -> None:
        if not queue_name:
            raise BrokerConfigurationError("queue_name must be non-empty")
        self._queues.setdefault(queue_name, Queue())

    def bind_queue(self, *, routing_key: str, queue_name: str) -> None:
        if not routing_key:
            raise BrokerConfigurationError("routing_key must be non-empty")
        self.declare_queue(queue_name)
        self._bindings[routing_key].add(queue_name)

    async def publish(self, *, routing_key: str, message: dict[str, Any]) -> list[PublishedMessage]:
        if not isinstance(message, dict):
            raise BrokerConfigurationError("message must be a dict")

        published: list[PublishedMessage] = []
        target_queues = self._resolve_queues(routing_key)
        for queue_name in target_queues:
            queue = self._queues[queue_name]
            payload = dict(message)
            await queue.put(payload)
            published.append(PublishedMessage(queue=queue_name, routing_key=routing_key, message=payload))
        return published

    async def consume(self, *, queue_name: str, timeout_seconds: float | None = None) -> dict[str, Any] | None:
        queue = self._queues.get(queue_name)
        if queue is None:
            raise BrokerConfigurationError(f"queue not declared: {queue_name}")
        if timeout_seconds is not None and timeout_seconds <= 0:
            try:
                return queue.get_nowait()
            except QueueEmpty:
                return None
        if timeout_seconds is None:
            return await queue.get()
        try:
            return await wait_for(queue.get(), timeout_seconds)
        except TimeoutError:
            return None

    def queue_size(self, queue_name: str) -> int:
        queue = self._queues.get(queue_name)
        if queue is None:
            raise BrokerConfigurationError(f"queue not declared: {queue_name}")
        return queue.qsize()

    async def drain(self, queue_name: str) -> list[dict[str, Any]]:
        queue = self._queues.get(queue_name)
        if queue is None:
            raise BrokerConfigurationError(f"queue not declared: {queue_name}")

        drained: list[dict[str, Any]] = []
        while not queue.empty():
            drained.append(await queue.get())
        return drained

    def _resolve_queues(self, routing_key: str) -> tuple[str, ...]:
        queues: set[str] = set()
        for pattern, bound_queues in self._bindings.items():
            if _topic_matches(pattern=pattern, routing_key=routing_key):
                queues.update(bound_queues)

        if routing_key in self._queues:
            queues.add(routing_key)
        return tuple(sorted(queues))


def _topic_matches(*, pattern: str, routing_key: str) -> bool:
    pattern_tokens = pattern.split(".")
    routing_tokens = routing_key.split(".")
    return _match_tokens(pattern_tokens=pattern_tokens, routing_tokens=routing_tokens)


def _match_tokens(*, pattern_tokens: list[str], routing_tokens: list[str]) -> bool:
    if not pattern_tokens:
        return not routing_tokens

    token = pattern_tokens[0]
    if token == "#":
        if len(pattern_tokens) == 1:
            return True
        for idx in range(len(routing_tokens) + 1):
            if _match_tokens(pattern_tokens=pattern_tokens[1:], routing_tokens=routing_tokens[idx:]):
                return True
        return False

    if not routing_tokens:
        return False
    if token in {"*", routing_tokens[0]}:
        return _match_tokens(pattern_tokens=pattern_tokens[1:], routing_tokens=routing_tokens[1:])
    return False
