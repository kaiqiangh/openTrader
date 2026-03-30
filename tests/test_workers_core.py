"""Core tests for services/workers/ — settings, helpers, builders.

TEST-001: Adds coverage for worker settings loading, helper utilities,
and builder functions (the 0%-coverage modules).
"""

from __future__ import annotations

import os
from argparse import Namespace
from decimal import Decimal

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers — _to_bool, _parse_csv_tokens, _safe_mapping, _safe_list,
#           _normalize_market_fetch_mode, time helpers
# ═══════════════════════════════════════════════════════════════════════════════


class TestToBool:
    """Exercise _to_bool with various truthy / falsy / invalid inputs."""

    @pytest.fixture()
    def fn(self):
        from services.workers.helpers import _to_bool
        return _to_bool

    @pytest.mark.parametrize("raw", ["true", "True", "TRUE", "1", "yes", "y", "on", "  true  "])
    def test_truthy_values(self, fn, raw: str) -> None:
        assert fn(raw) is True

    @pytest.mark.parametrize("raw", ["false", "False", "FALSE", "0", "no", "n", "off", "  false  "])
    def test_falsy_values(self, fn, raw: str) -> None:
        assert fn(raw) is False

    @pytest.mark.parametrize("raw", ["maybe", "2", "", "  ", "nah"])
    def test_invalid_raises(self, fn, raw: str) -> None:
        with pytest.raises(ValueError, match="invalid boolean value"):
            fn(raw)


class TestParseCsvTokens:
    """Exercise _parse_csv_tokens edge cases."""

    @pytest.fixture()
    def fn(self):
        from services.workers.helpers import _parse_csv_tokens
        return _parse_csv_tokens

    def test_none_returns_empty(self, fn) -> None:
        assert fn(None) == ()

    def test_empty_string_returns_empty(self, fn) -> None:
        assert fn("") == ()

    def test_single_token(self, fn) -> None:
        assert fn("binance") == ("binance",)

    def test_multiple_tokens(self, fn) -> None:
        assert fn("binance,bitget") == ("binance", "bitget")

    def test_strips_whitespace(self, fn) -> None:
        assert fn("  a , b , c  ") == ("a", "b", "c")

    def test_filters_empty_between_commas(self, fn) -> None:
        assert fn("a,,b") == ("a", "b")

    def test_all_empty_tokens(self, fn) -> None:
        assert fn(",,,") == ()


class TestSafeMapping:
    """Exercise _safe_mapping type coercion."""

    @pytest.fixture()
    def fn(self):
        from services.workers.helpers import _safe_mapping
        return _safe_mapping

    def test_dict_passthrough(self, fn) -> None:
        assert fn({"a": 1}) == {"a": 1}

    def test_non_mapping_returns_empty(self, fn) -> None:
        assert fn("not a mapping") == {}
        assert fn(None) == {}
        assert fn(42) == {}

    def test_returns_copy(self, fn) -> None:
        original: dict[str, int] = {"k": 1}
        result = fn(original)
        result["k"] = 99
        assert original["k"] == 1  # didn't mutate


class TestSafeList:
    """Exercise _safe_list type coercion."""

    @pytest.fixture()
    def fn(self):
        from services.workers.helpers import _safe_list
        return _safe_list

    def test_list_passthrough(self, fn) -> None:
        assert fn([1, 2]) == [1, 2]

    def test_non_list_returns_empty(self, fn) -> None:
        assert fn("not a list") == []
        assert fn(None) == []
        assert fn({"a": 1}) == []


class TestNormalizeMarketFetchMode:
    """Exercise _normalize_market_fetch_mode."""

    @pytest.fixture()
    def fn(self):
        from services.workers.helpers import _normalize_market_fetch_mode
        return _normalize_market_fetch_mode

    @pytest.mark.parametrize("raw", ["rest", "Rest", "REST", "restful", "http", "  rest  "])
    def test_rest_variants(self, fn, raw: str) -> None:
        assert fn(raw) == "rest"

    @pytest.mark.parametrize("raw", ["websocket", "ws", "Websocket", "WS"])
    def test_ws_variants(self, fn, raw: str) -> None:
        assert fn(raw) == "websocket"

    def test_invalid_raises(self, fn) -> None:
        with pytest.raises(ValueError):
            fn("grpc")


class TestTimeHelpers:
    """Exercise _utc_now_ms and _utc_now_iso."""

    def test_utc_now_ms_returns_int(self) -> None:
        from services.workers.helpers import _utc_now_ms
        result = _utc_now_ms()
        assert isinstance(result, int)
        assert result > 1_700_000_000_000  # sane epoch

    def test_utc_now_iso_ends_with_z(self) -> None:
        from services.workers.helpers import _utc_now_iso
        result = _utc_now_iso()
        assert result.endswith("Z")
        assert "T" in result


class TestWorkerActivitySnapshot:
    """Exercise _worker_activity_snapshot with various worker shapes."""

    @pytest.fixture()
    def fn(self):
        from services.workers.helpers import _worker_activity_snapshot
        return _worker_activity_snapshot

    def test_no_attribute(self, fn) -> None:
        class Bare:
            pass
        assert fn(Bare()) == {}

    def test_non_callable(self, fn) -> None:
        class AttrOnly:
            activity_snapshot = "not_callable"
        assert fn(AttrOnly()) == {}

    def test_raises_returns_empty(self, fn) -> None:
        class Boom:
            def activity_snapshot(self):
                raise RuntimeError("boom")
        assert fn(Boom()) == {}

    def test_returns_non_mapping(self, fn) -> None:
        class ReturnsList:
            def activity_snapshot(self):
                return [1, 2, 3]
        assert fn(ReturnsList()) == {}

    def test_returns_mapping(self, fn) -> None:
        class Good:
            def activity_snapshot(self):
                return {"trace_id": "abc"}
        assert fn(Good()) == {"trace_id": "abc"}


class TestCorrelationFromActivity:
    """Exercise _correlation_from_activity key extraction."""

    @pytest.fixture()
    def fn(self):
        from services.workers.helpers import _correlation_from_activity
        return _correlation_from_activity

    def test_flat_mapping(self, fn) -> None:
        result = fn({"trace_id": "t1", "decision_id": "d1"})
        assert result["trace_id"] == "t1"
        assert result["decision_id"] == "d1"

    def test_nested_mapping(self, fn) -> None:
        result = fn({"inner": {"order_id": "o99"}})
        assert result["order_id"] == "o99"

    def test_non_mapping_returns_empty(self, fn) -> None:
        assert fn(None) == {}
        assert fn("nope") == {}

    def test_depth_limit(self, fn) -> None:
        deep = {"l1": {"l2": {"l3": {"l4": {"trace_id": "too_deep"}}}}}
        result = fn(deep)
        assert result["trace_id"] is None  # depth > 3


class TestMaybeUuid:
    """Exercise _maybe_uuid validation."""

    @pytest.fixture()
    def fn(self):
        from services.workers.helpers import _maybe_uuid
        return _maybe_uuid

    def test_valid_uuid(self, fn) -> None:
        result = fn("550e8400-e29b-41d4-a716-446655440000")
        assert result == "550e8400-e29b-41d4-a716-446655440000"

    def test_invalid_returns_none(self, fn) -> None:
        assert fn("not-a-uuid") is None
        assert fn("") is None
        assert fn(None) is None

    def test_whitespace_stripped(self, fn) -> None:
        result = fn("  550e8400-e29b-41d4-a716-446655440000  ")
        assert result == "550e8400-e29b-41d4-a716-446655440000"


# ═══════════════════════════════════════════════════════════════════════════════
# Settings — _parse_args, load_runtime_worker_settings
# ═══════════════════════════════════════════════════════════════════════════════


class TestParseArgs:
    """Exercise _parse_args for each worker choice."""

    @pytest.fixture()
    def parse(self):
        from services.workers.settings import _parse_args
        return _parse_args

    @pytest.mark.parametrize("worker", ["market", "orchestrator", "simulation", "oms", "news", "execution_lifecycle"])
    def test_valid_worker_choices(self, parse, worker: str) -> None:
        ns = parse(["--worker", worker])
        assert ns.worker == worker

    def test_missing_worker_raises(self, parse) -> None:
        with pytest.raises(SystemExit):
            parse([])

    def test_invalid_worker_raises(self, parse) -> None:
        with pytest.raises(SystemExit):
            parse(["--worker", "nonexistent"])

    def test_once_flag(self, parse) -> None:
        ns = parse(["--worker", "market", "--once"])
        assert ns.once is True

    def test_validate_only_flag(self, parse) -> None:
        ns = parse(["--worker", "market", "--validate-only"])
        assert ns.validate_only is True

    def test_max_idle_cycles(self, parse) -> None:
        ns = parse(["--worker", "market", "--max-idle-cycles", "10"])
        assert ns.max_idle_cycles == 10

    def test_custom_symbol(self, parse) -> None:
        ns = parse(["--worker", "market", "--symbol", "ETH/USDT"])
        assert ns.symbol == "ETH/USDT"

    def test_custom_strategy_id(self, parse) -> None:
        ns = parse(["--worker", "market", "--strategy-id", "my-strat"])
        assert ns.strategy_id == "my-strat"

    def test_poll_timeout(self, parse) -> None:
        ns = parse(["--worker", "market", "--poll-timeout-seconds", "2.0"])
        assert ns.poll_timeout_seconds == 2.0

    def test_broker_backend_inmemory(self, parse) -> None:
        ns = parse(["--worker", "market", "--broker-backend", "inmemory"])
        assert ns.broker_backend == "inmemory"


class TestLoadRuntimeWorkerSettings:
    """Exercise load_runtime_worker_settings with synthetic Namespace objects."""

    @pytest.fixture()
    def load(self):
        from services.workers.settings import load_runtime_worker_settings
        return load_runtime_worker_settings

    @staticmethod
    def _make_ns(**overrides) -> Namespace:
        defaults = dict(
            worker="market",
            broker_backend=None,
            topology_path="config/rabbitmq/topology.json",
            mode=None,
            symbol=None,
            strategy_id=None,
            once=False,
            validate_only=False,
            max_idle_cycles=0,
            poll_timeout_seconds=0.5,
            idle_sleep_seconds=0.5,
            bootstrap_topology=False,
        )
        defaults.update(overrides)
        return Namespace(**defaults)

    def test_defaults_applied(self, load) -> None:
        settings = load(self._make_ns())
        assert settings.worker == "market"
        assert settings.broker_backend == "rabbitmq_http"  # default
        assert settings.mode == "MOCK"  # default
        assert settings.symbol == "BTC/USDT"
        assert settings.strategy_id == "default-strategy"
        assert settings.once is False
        assert settings.validate_only is False
        assert settings.require_database is True

    def test_explicit_overrides_applied(self, load) -> None:
        settings = load(self._make_ns(
            worker="orchestrator",
            broker_backend="inmemory",
            mode="REAL",
            symbol="ETH/USDT",
            strategy_id="custom",
            once=True,
            validate_only=True,
        ))
        assert settings.worker == "orchestrator"
        assert settings.broker_backend == "inmemory"
        assert settings.mode == "REAL"
        assert settings.symbol == "ETH/USDT"
        assert settings.strategy_id == "custom"
        assert settings.once is True
        assert settings.validate_only is True

    def test_max_idle_cycles_floor_at_zero(self, load) -> None:
        settings = load(self._make_ns(max_idle_cycles=-5))
        assert settings.max_idle_cycles == 0

    def test_poll_timeout_floor_at_zero(self, load) -> None:
        settings = load(self._make_ns(poll_timeout_seconds=-1.0))
        assert settings.poll_timeout_seconds == 0.0

    def test_broker_backend_stripped_and_lowered(self, load) -> None:
        settings = load(self._make_ns(broker_backend="  InMemory  "))
        assert settings.broker_backend == "inmemory"

    def test_symbol_uppercased(self, load) -> None:
        settings = load(self._make_ns(symbol="eth/usdt"))
        assert settings.symbol == "ETH/USDT"

    def test_worker_choices_all_accepted(self, load) -> None:
        for worker in ("market", "orchestrator", "simulation", "oms", "news", "execution_lifecycle"):
            settings = load(self._make_ns(worker=worker))
            assert settings.worker == worker


class TestValidateRuntimeBackendPolicy:
    """Exercise _validate_runtime_backend_policy edge cases."""

    def test_inmemory_blocked_when_require_database(self) -> None:
        from services.workers.settings import (
            RuntimeWorkerSettings,
            _validate_runtime_backend_policy,
        )
        settings = RuntimeWorkerSettings(
            worker="market",
            broker_backend="inmemory",
            topology_path="topology.json",
            mode="MOCK",
            symbol="BTC/USDT",
            strategy_id="s1",
            once=False,
            validate_only=False,
            max_idle_cycles=0,
            poll_timeout_seconds=0.5,
            idle_sleep_seconds=0.5,
            bootstrap_topology=False,
            portfolio_base_balance_usd=100_000.0,
            require_database=True,
        )
        with pytest.raises(ValueError, match="inmemory broker backend is disabled"):
            _validate_runtime_backend_policy(settings=settings)

    def test_inmemory_allowed_when_not_require_database(self) -> None:
        from services.workers.settings import (
            RuntimeWorkerSettings,
            _validate_runtime_backend_policy,
        )
        settings = RuntimeWorkerSettings(
            worker="market",
            broker_backend="inmemory",
            topology_path="topology.json",
            mode="MOCK",
            symbol="BTC/USDT",
            strategy_id="s1",
            once=False,
            validate_only=False,
            max_idle_cycles=0,
            poll_timeout_seconds=0.5,
            idle_sleep_seconds=0.5,
            bootstrap_topology=False,
            portfolio_base_balance_usd=100_000.0,
            require_database=False,
        )
        # should not raise
        _validate_runtime_backend_policy(settings=settings)


# ═══════════════════════════════════════════════════════════════════════════════
# Builders — build_runtime_broker
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildRuntimeBroker:
    """Exercise build_runtime_broker with known backends."""

    def test_inmemory_backend(self, tmp_path) -> None:
        from services.workers.builders import build_runtime_broker
        topo = tmp_path / "topology.json"
        topo.write_text("{}")
        broker = build_runtime_broker(backend="inmemory", topology_path=str(topo))
        assert broker is not None

    def test_invalid_backend_raises(self) -> None:
        from services.workers.builders import build_runtime_broker
        with pytest.raises(ValueError, match="RUNTIME_BROKER_BACKEND"):
            build_runtime_broker(backend="kafka", topology_path="nonexistent.json")

    def test_backend_is_case_insensitive(self, tmp_path) -> None:
        from services.workers.builders import build_runtime_broker
        topo = tmp_path / "topology.json"
        topo.write_text("{}")
        broker = build_runtime_broker(backend="  InMemory  ", topology_path=str(topo))
        assert broker is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers — _resolve_requested_quantity (verify existing tests still hold)
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveRequestedQuantity:
    """Additional edge cases for _resolve_requested_quantity."""

    @pytest.fixture()
    def fn(self):
        from services.workers.helpers import _resolve_requested_quantity
        return _resolve_requested_quantity

    def test_none_raises(self, fn) -> None:
        with pytest.raises(ValueError, match="requested_quantity must be positive"):
            fn(None)

    def test_zero_raises(self, fn) -> None:
        with pytest.raises(ValueError, match="requested_quantity must be positive"):
            fn(0.0)

    def test_negative_converted_to_positive(self, fn) -> None:
        result = fn(-2.5)
        assert result == Decimal("2.5")

    def test_positive_passthrough(self, fn) -> None:
        result = fn(3.14)
        assert result == Decimal("3.14")

    def test_very_small_positive(self, fn) -> None:
        result = fn(0.00000001)
        assert result > 0

    def test_large_value(self, fn) -> None:
        result = fn(999_999_999.0)
        assert result == Decimal("999999999.0")


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers — RSS / news helpers
# ═══════════════════════════════════════════════════════════════════════════════


class TestNewsHelpers:
    """Exercise news-related helpers."""

    def test_default_rss_feeds_non_empty(self) -> None:
        from services.workers.helpers import _default_news_rss_feeds
        feeds = _default_news_rss_feeds()
        assert len(feeds) >= 2
        assert all(f.startswith("http") for f in feeds)

    def test_resolve_news_source_mode_require_db(self) -> None:
        from services.workers.helpers import _resolve_news_source_mode
        assert _resolve_news_source_mode(require_database=True) == "real"

    def test_resolve_news_source_mode_no_db(self) -> None:
        from services.workers.helpers import _resolve_news_source_mode
        assert _resolve_news_source_mode(require_database=False) == "mock"

    def test_resolve_news_source_mode_invalid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from services.workers.helpers import _resolve_news_source_mode
        monkeypatch.setenv("NEWS_SOURCE_MODE", "invalid")
        with pytest.raises(ValueError, match="NEWS_SOURCE_MODE"):
            _resolve_news_source_mode(require_database=False)

    def test_infer_source_name(self) -> None:
        from services.workers.helpers import _infer_source_name
        assert _infer_source_name("https://www.coindesk.com/rss") == "coindesk.com"
        assert _infer_source_name("https://cointelegraph.com/rss") == "cointelegraph.com"

    def test_build_source_item_id_deterministic(self) -> None:
        from services.workers.helpers import _build_source_item_id
        id1 = _build_source_item_id(source="test", link="https://example.com/a")
        id2 = _build_source_item_id(source="test", link="https://example.com/a")
        assert id1 == id2

    def test_build_source_item_id_truncates_long(self) -> None:
        from services.workers.helpers import _build_source_item_id
        long_link = "https://example.com/" + "a" * 200
        result = _build_source_item_id(source="src", link=long_link)
        # Should be hashed, so bounded length
        assert len(result) <= 128
