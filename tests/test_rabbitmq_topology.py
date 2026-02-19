from pathlib import Path
import json


def test_rabbitmq_topology_file_exists() -> None:
    assert Path("config/rabbitmq/topology.json").exists()


def test_rabbitmq_topology_has_required_exchanges_and_queues() -> None:
    payload = json.loads(Path("config/rabbitmq/topology.json").read_text(encoding="utf-8"))

    exchange_names = {item["name"] for item in payload["exchanges"]}
    queue_names = {item["name"] for item in payload["queues"]}

    assert "market.events" in exchange_names
    assert "strategy.events" in exchange_names
    assert "execution.events" in exchange_names
    assert "oms.events" in exchange_names

    assert "market.canonical" in queue_names
    assert "strategy.events.lifecycle" in queue_names
    assert "execution.intent.mock" in queue_names
    assert "execution.intent.real" in queue_names
    assert "execution.intent.real.lifecycle" in queue_names
    assert "oms.events.order_updates" in queue_names
    assert "dlq.execution.intent.real" in queue_names


def test_rabbitmq_topology_has_bindings() -> None:
    payload = json.loads(Path("config/rabbitmq/topology.json").read_text(encoding="utf-8"))
    assert len(payload["bindings"]) > 0
