from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib import parse
import httpx
import asyncio
import base64
import json
import os

from services.shared.runtime.env_loader import load_dotenv_file

_DEFAULT_EXCHANGE_BY_PREFIX: dict[str, str] = {
    "market.": "market.events",
    "strategy.": "strategy.events",
    "agent.": "strategy.events",
    "execution.": "execution.events",
    "oms.": "oms.events",
    "notify.": "notify.events",
}


class RabbitMQHTTPBrokerError(RuntimeError):
    def __init__(
        self, *, message: str, status_code: int | None = None, body: str | None = None
    ) -> None:
        self.status_code = status_code
        self.body = body
        suffix = ""
        if status_code is not None:
            suffix += f" [{status_code}]"
        if body:
            suffix += f" {body}"
        super().__init__(f"{message}{suffix}")


RabbitMQHTTPFetchFn = Callable[[str, str, str, str, float], list[dict[str, Any]]]
RabbitMQHTTPPublishFn = Callable[[str, str, str, str, str, Mapping[str, Any], float], None]
RabbitMQHTTPDeclareQueueFn = Callable[[str, str, str, str, float], None]
RabbitMQHTTPDeclareExchangeFn = Callable[[str, str, str, str, float], None]
RabbitMQHTTPBindQueueFn = Callable[[str, str, str, str, str, float], None]


class RabbitMQHTTPTopicBroker:
    """RabbitMQ topic broker adapter using the management HTTP API."""

    def __init__(
        self,
        *,
        api_base_url: str,
        username: str,
        password: str,
        request_timeout_seconds: float = 2.0,
        topology_path: str | Path | None = "config/rabbitmq/topology.json",
        fetch_fn: RabbitMQHTTPFetchFn | None = None,
        publish_fn: RabbitMQHTTPPublishFn | None = None,
        declare_queue_fn: RabbitMQHTTPDeclareQueueFn | None = None,
        declare_exchange_fn: RabbitMQHTTPDeclareExchangeFn | None = None,
        bind_queue_fn: RabbitMQHTTPBindQueueFn | None = None,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.username = username
        self.password = password
        self.request_timeout_seconds = request_timeout_seconds

        self._fetch_fn = fetch_fn or _default_rabbitmq_http_fetch
        self._publish_fn = publish_fn or _default_rabbitmq_http_publish
        self._declare_queue_fn = declare_queue_fn or _default_rabbitmq_http_declare_queue
        self._declare_exchange_fn = declare_exchange_fn or _default_rabbitmq_http_declare_exchange
        self._bind_queue_fn = bind_queue_fn or _default_rabbitmq_http_bind_queue

        self._declared_queues: set[str] = set()
        self._bootstrapped_topology = False
        self._exchange_routes: list[tuple[str, str]] = []
        self._topology_payload = _load_topology_payload(topology_path)
        self._exchange_routes = _exchange_routes_from_topology(self._topology_payload)

    @classmethod
    def from_env(
        cls,
        *,
        topology_path: str | Path = "config/rabbitmq/topology.json",
    ) -> RabbitMQHTTPTopicBroker:
        load_dotenv_file()
        api_base = os.getenv(
            "RUNTIME_RABBITMQ_HTTP_API_URL",
            os.getenv("NOTIFY_RABBITMQ_HTTP_API_URL", "http://rabbitmq:15672/api"),
        )
        username = os.getenv("RABBITMQ_DEFAULT_USER", "").strip()
        password = os.getenv("RABBITMQ_DEFAULT_PASS", "").strip()
        if not username or not password:
            raise RuntimeError("RABBITMQ_DEFAULT_USER and RABBITMQ_DEFAULT_PASS must be set")
        timeout_seconds = float(os.getenv("RUNTIME_BROKER_HTTP_TIMEOUT_SECONDS", "2.0"))
        return cls(
            api_base_url=api_base,
            username=username,
            password=password,
            request_timeout_seconds=timeout_seconds,
            topology_path=topology_path,
        )

    async def bootstrap_topology(self) -> None:
        if self._bootstrapped_topology:
            return

        exchanges = _safe_list(self._topology_payload.get("exchanges"))
        queues = _safe_list(self._topology_payload.get("queues"))
        bindings = _safe_list(self._topology_payload.get("bindings"))

        for exchange in exchanges:
            if not isinstance(exchange, Mapping):
                continue
            name = exchange.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            await asyncio.to_thread(
                self._declare_exchange_fn,
                self.api_base_url,
                self.username,
                self.password,
                name,
                self.request_timeout_seconds,
            )

        for queue in queues:
            if not isinstance(queue, Mapping):
                continue
            name = queue.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            await asyncio.to_thread(
                self._declare_queue_fn,
                self.api_base_url,
                self.username,
                self.password,
                name,
                self.request_timeout_seconds,
            )
            self._declared_queues.add(name)

        for binding in bindings:
            if not isinstance(binding, Mapping):
                continue
            exchange_name = binding.get("exchange")
            queue_name = binding.get("queue")
            routing_key = binding.get("routing_key")
            if not isinstance(exchange_name, str):
                continue
            if not isinstance(queue_name, str):
                continue
            if not isinstance(routing_key, str):
                continue
            await asyncio.to_thread(
                self._bind_queue_fn,
                self.api_base_url,
                self.username,
                self.password,
                exchange_name,
                queue_name,
                routing_key,
                self.request_timeout_seconds,
            )

        self._bootstrapped_topology = True

    async def publish(self, *, routing_key: str, message: Mapping[str, Any]) -> None:
        exchange_name = self._resolve_exchange_for_routing_key(routing_key)
        await asyncio.to_thread(
            self._publish_fn,
            self.api_base_url,
            self.username,
            self.password,
            exchange_name,
            routing_key,
            dict(message),
            self.request_timeout_seconds,
        )

    async def consume(
        self, *, queue_name: str, timeout_seconds: float | None = None
    ) -> dict[str, Any] | None:
        _ = timeout_seconds
        try:
            rows = await asyncio.to_thread(
                self._fetch_fn,
                self.api_base_url,
                self.username,
                self.password,
                queue_name,
                self.request_timeout_seconds,
            )
        except RabbitMQHTTPBrokerError as exc:
            body = exc.body or ""
            if exc.status_code == 404 and "queue_not_found" in body:
                await self._declare_queue(queue_name)
                return None
            raise

        if not rows:
            return None
        payload = rows[0].get("payload")
        if isinstance(payload, Mapping):
            return dict(payload)
        if isinstance(payload, str):
            parsed = json.loads(payload)
            if isinstance(parsed, Mapping):
                return dict(parsed)
        raise RabbitMQHTTPBrokerError(message="RabbitMQ HTTP payload is not a JSON object envelope")

    async def _declare_queue(self, queue_name: str) -> None:
        if queue_name in self._declared_queues:
            return
        await asyncio.to_thread(
            self._declare_queue_fn,
            self.api_base_url,
            self.username,
            self.password,
            queue_name,
            self.request_timeout_seconds,
        )
        self._declared_queues.add(queue_name)

    def _resolve_exchange_for_routing_key(self, routing_key: str) -> str:
        for pattern, exchange_name in self._exchange_routes:
            if _topic_matches(pattern=pattern, routing_key=routing_key):
                return exchange_name

        for prefix, exchange_name in _DEFAULT_EXCHANGE_BY_PREFIX.items():
            if routing_key.startswith(prefix):
                return exchange_name

        raise RabbitMQHTTPBrokerError(
            message=f"unable to resolve exchange for routing key '{routing_key}'"
        )


def _load_topology_payload(path: str | Path | None) -> Mapping[str, Any]:
    if path is None:
        return {}
    topology_path = Path(path)
    if not topology_path.exists():
        return {}
    payload = json.loads(topology_path.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping):
        return payload
    return {}


def _exchange_routes_from_topology(payload: Mapping[str, Any]) -> list[tuple[str, str]]:
    bindings = _safe_list(payload.get("bindings"))
    routes: list[tuple[str, str]] = []
    for binding in bindings:
        if not isinstance(binding, Mapping):
            continue
        exchange_name = binding.get("exchange")
        routing_key = binding.get("routing_key")
        if not isinstance(exchange_name, str) or not exchange_name.strip():
            continue
        if not isinstance(routing_key, str) or not routing_key.strip():
            continue
        routes.append((routing_key, exchange_name))

    # More specific patterns first (fewer wildcards, longer token count).
    routes.sort(key=lambda item: (_pattern_weight(item[0]), len(item[0])), reverse=True)
    return routes


def _pattern_weight(pattern: str) -> int:
    tokens = pattern.split(".")
    weight = 0
    for token in tokens:
        if token in {"*", "#"}:
            continue
        weight += 1
    return weight


def _safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _default_rabbitmq_http_fetch(
    api_base_url: str,
    username: str,
    password: str,
    queue_name: str,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    queue_ref = parse.quote(queue_name, safe="")
    url = f"{api_base_url}/queues/%2F/{queue_ref}/get"
    payload = json.dumps(
        {
            "count": 1,
            "ackmode": "ack_requeue_false",
            "encoding": "auto",
            "truncate": 50000,
        }
    ).encode("utf-8")
    raw = _request_json(
        url=url,
        username=username,
        password=password,
        method="POST",
        payload=payload,
        timeout_seconds=timeout_seconds,
    )
    parsed = json.loads(raw) if raw else []
    if isinstance(parsed, list):
        return [dict(row) for row in parsed if isinstance(row, dict)]
    return []


def _default_rabbitmq_http_publish(
    api_base_url: str,
    username: str,
    password: str,
    exchange_name: str,
    routing_key: str,
    message: Mapping[str, Any],
    timeout_seconds: float,
) -> None:
    exchange_ref = parse.quote(exchange_name, safe="")
    url = f"{api_base_url}/exchanges/%2F/{exchange_ref}/publish"
    payload = json.dumps(
        {
            "properties": {"delivery_mode": 2},
            "routing_key": routing_key,
            "payload": json.dumps(dict(message), ensure_ascii=True),
            "payload_encoding": "string",
        }
    ).encode("utf-8")
    raw = _request_json(
        url=url,
        username=username,
        password=password,
        method="POST",
        payload=payload,
        timeout_seconds=timeout_seconds,
    )
    parsed = json.loads(raw) if raw else {}
    if not isinstance(parsed, Mapping) or not parsed.get("routed"):
        raise RabbitMQHTTPBrokerError(message="RabbitMQ publish was not routed")


def _default_rabbitmq_http_declare_queue(
    api_base_url: str,
    username: str,
    password: str,
    queue_name: str,
    timeout_seconds: float,
) -> None:
    queue_ref = parse.quote(queue_name, safe="")
    url = f"{api_base_url}/queues/%2F/{queue_ref}"
    payload = json.dumps({"durable": True, "auto_delete": False, "arguments": {}}).encode("utf-8")
    _request_json(
        url=url,
        username=username,
        password=password,
        method="PUT",
        payload=payload,
        timeout_seconds=timeout_seconds,
    )


def _default_rabbitmq_http_declare_exchange(
    api_base_url: str,
    username: str,
    password: str,
    exchange_name: str,
    timeout_seconds: float,
) -> None:
    exchange_ref = parse.quote(exchange_name, safe="")
    url = f"{api_base_url}/exchanges/%2F/{exchange_ref}"
    payload = json.dumps(
        {"type": "topic", "durable": True, "auto_delete": False, "arguments": {}}
    ).encode("utf-8")
    _request_json(
        url=url,
        username=username,
        password=password,
        method="PUT",
        payload=payload,
        timeout_seconds=timeout_seconds,
    )


def _default_rabbitmq_http_bind_queue(
    api_base_url: str,
    username: str,
    password: str,
    exchange_name: str,
    queue_name: str,
    routing_key: str,
    timeout_seconds: float,
) -> None:
    exchange_ref = parse.quote(exchange_name, safe="")
    queue_ref = parse.quote(queue_name, safe="")
    url = f"{api_base_url}/bindings/%2F/e/{exchange_ref}/q/{queue_ref}"
    payload = json.dumps({"routing_key": routing_key, "arguments": {}}).encode("utf-8")
    _request_json(
        url=url,
        username=username,
        password=password,
        method="POST",
        payload=payload,
        timeout_seconds=timeout_seconds,
    )


def _request_json(
    *,
    url: str,
    username: str,
    password: str,
    method: str,
    payload: bytes | None,
    timeout_seconds: float,
) -> str:
    auth_raw = f"{username}:{password}".encode("utf-8")
    auth_header = base64.b64encode(auth_raw).decode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {auth_header}",
    }
    try:
        with httpx.Client(timeout=timeout_seconds, verify=True) as client:
            response = client.request(method, url, content=payload, headers=headers)
            response.raise_for_status()
            return response.text
    except httpx.HTTPStatusError as exc:
        body = exc.response.text
        raise RabbitMQHTTPBrokerError(
            message="RabbitMQ HTTP request failed",
            status_code=int(exc.response.status_code),
            body=body,
        ) from exc
    except httpx.HTTPError as exc:
        raise RabbitMQHTTPBrokerError(message=f"RabbitMQ HTTP request failed: {exc}") from exc


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
            if _match_tokens(
                pattern_tokens=pattern_tokens[1:], routing_tokens=routing_tokens[idx:]
            ):
                return True
        return False

    if not routing_tokens:
        return False
    if token in {"*", routing_tokens[0]}:
        return _match_tokens(pattern_tokens=pattern_tokens[1:], routing_tokens=routing_tokens[1:])
    return False
