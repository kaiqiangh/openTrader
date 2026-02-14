from pathlib import Path
import json


def test_redis_namespace_spec_exists() -> None:
    assert Path("config/redis/namespaces.json").exists()


def test_redis_namespaces_include_core_domains() -> None:
    payload = json.loads(Path("config/redis/namespaces.json").read_text(encoding="utf-8"))
    names = {item["name"] for item in payload["namespaces"]}

    assert "memory.decision" in names
    assert "snapshot.market" in names
    assert "rate_limit" in names
    assert "lock" in names


def test_redis_namespace_entries_have_ttl_and_key_pattern() -> None:
    payload = json.loads(Path("config/redis/namespaces.json").read_text(encoding="utf-8"))

    for item in payload["namespaces"]:
        assert item["key_pattern"]
        assert item["ttl_seconds"] > 0


def test_redis_namespace_doc_exists_and_mentions_mode_isolation() -> None:
    content = Path("docs/redis_namespace_strategy.md").read_text(encoding="utf-8")
    assert "config/redis/namespaces.json" in content
    assert "MOCK" in content
    assert "REAL" in content
