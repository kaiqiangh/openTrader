"""Edge case tests for boundary values, empty inputs, and error paths."""

from __future__ import annotations

from decimal import Decimal

import pytest


class TestFillReconciliationEdgeCases:
    """Edge cases for fill reconciliation engine."""

    def test_empty_lifecycle_events(self):
        from services.oms.fill_reconciliation import (
            FillReconciliationEngine,
            ReconciliationOrder,
        )

        engine = FillReconciliationEngine()
        order = ReconciliationOrder(
            order_id="o1",
            symbol="BTC/USDT",
            mode="MOCK",
            requested_quantity=Decimal("1.0"),
            status="NEW",
        )
        result = engine.reconcile(order=order)
        assert result.status == "NEW"
        assert result.filled_quantity == Decimal("0")
        assert not result.changed

    def test_zero_requested_quantity(self):
        from services.oms.fill_reconciliation import (
            FillReconciliationEngine,
            ReconciliationOrder,
        )

        engine = FillReconciliationEngine()
        order = ReconciliationOrder(
            order_id="o1",
            symbol="BTC/USDT",
            mode="MOCK",
            requested_quantity=Decimal("0"),
            status="NEW",
        )
        result = engine.reconcile(order=order)
        # Can't derive FILLED/PARTIALLY_FILLED without requested_quantity
        assert result.status == "NEW"

    def test_duplicate_fills_deduped(self):
        from services.oms.fill_reconciliation import (
            FillReconciliationEngine,
            LifecycleEvent,
            ReconciliationFill,
            ReconciliationOrder,
        )

        engine = FillReconciliationEngine()
        order = ReconciliationOrder(
            order_id="o1",
            symbol="BTC/USDT",
            mode="MOCK",
            requested_quantity=Decimal("2.0"),
            status="OPEN",
        )
        fill = ReconciliationFill(
            fill_id="f1", order_id="o1", quantity=Decimal("1.0"), price=Decimal("50000")
        )
        events = [
            LifecycleEvent(event_type="oms.order.filled", fill=fill),
            LifecycleEvent(event_type="oms.order.filled", fill=fill),  # duplicate
        ]
        result = engine.reconcile(order=order, lifecycle_events=events)
        assert result.filled_quantity == Decimal("1.0")  # not 2.0


class TestPositionEngineEdgeCases:
    """Edge cases for position engine."""

    def test_zero_quantity_position_rejected(self):
        from services.oms.position_engine import PositionEngine, PositionEngineError, PositionFill

        engine = PositionEngine()
        fill = PositionFill(
            order_id="o1",
            mode="MOCK",
            symbol="BTC/USDT",
            side="BUY",
            quantity=Decimal("0"),
            price=Decimal("50000"),
            fee=Decimal("0"),
            filled_at="2026-01-01T00:00:00Z",
        )
        with pytest.raises(PositionEngineError, match="fill.quantity must be positive"):
            engine.apply_fill(position=None, fill=fill)

    def test_sell_on_empty_position(self):
        from services.oms.position_engine import PositionEngine, PositionFill

        engine = PositionEngine()
        fill = PositionFill(
            order_id="o1",
            mode="MOCK",
            symbol="BTC/USDT",
            side="SELL",
            quantity=Decimal("1"),
            price=Decimal("50000"),
            fee=Decimal("0"),
            filled_at="2026-01-01T00:00:00Z",
        )
        result = engine.apply_fill(position=None, fill=fill)
        # SELL on empty position = short
        assert result.current.quantity == Decimal("-1")


class TestRiskRulesEdgeCases:
    """Edge cases for risk rules."""

    def test_validate_order_rejects_zero_quantity(self):
        from services.oms.risk_rules import ProposedOrder, _validate_order

        order = ProposedOrder(
            mode="MOCK", symbol="BTC/USDT", side="BUY", quantity=0.0, price=50000.0
        )
        with pytest.raises(Exception, match="quantity must be positive"):
            _validate_order(order)

    def test_validate_order_rejects_zero_price(self):
        from services.oms.risk_rules import ProposedOrder, _validate_order

        order = ProposedOrder(mode="MOCK", symbol="BTC/USDT", side="BUY", quantity=1.0, price=0.0)
        with pytest.raises(Exception, match="price must be positive"):
            _validate_order(order)

    def test_validate_order_accepts_decimal_quantity(self):
        from services.oms.risk_rules import ProposedOrder, _validate_order

        order = ProposedOrder(
            mode="MOCK",
            symbol="BTC/USDT",
            side="BUY",
            quantity=Decimal("0.001"),
            price=Decimal("50000"),
        )
        result = _validate_order(order)
        assert result.symbol == "BTC/USDT"

    def test_validate_order_rejects_sub_epsilon_quantity(self):
        from services.oms.risk_rules import ProposedOrder, _validate_order

        order = ProposedOrder(
            mode="MOCK", symbol="BTC/USDT", side="BUY", quantity=1e-10, price=50000.0
        )
        with pytest.raises(Exception, match="quantity must be positive"):
            _validate_order(order)


class TestHelpersEdgeCases:
    """Edge cases for worker helpers."""

    def test_resolve_requested_quantity_zero(self):
        from services.workers.main import _resolve_requested_quantity

        with pytest.raises(ValueError, match="requested_quantity must be positive"):
            _resolve_requested_quantity(0.0)

    def test_resolve_requested_quantity_none(self):
        from services.workers.main import _resolve_requested_quantity

        with pytest.raises(ValueError):
            _resolve_requested_quantity(None)

    def test_resolve_requested_quantity_negative_converts(self):
        from services.workers.main import _resolve_requested_quantity

        assert _resolve_requested_quantity(-5.0) == 5.0

    def test_resolve_news_source_mode_no_db(self):
        from services.workers.helpers import _resolve_news_source_mode

        assert _resolve_news_source_mode(require_database=False) == "mock"

    def test_resolve_news_source_mode_with_db(self):
        from services.workers.helpers import _resolve_news_source_mode

        assert _resolve_news_source_mode(require_database=True) == "real"

    def test_parse_csv_tokens_empty(self):
        from services.workers.helpers import _parse_csv_tokens

        assert _parse_csv_tokens("") == ()
        assert _parse_csv_tokens(None) == ()

    def test_parse_csv_tokens_single(self):
        from services.workers.helpers import _parse_csv_tokens

        assert _parse_csv_tokens("one") == ("one",)

    def test_parse_csv_tokens_multi(self):
        from services.workers.helpers import _parse_csv_tokens

        assert _parse_csv_tokens("a,b,c") == ("a", "b", "c")

    def test_to_bool_edge_cases(self):
        from services.workers.helpers import _to_bool

        assert _to_bool("true") is True
        assert _to_bool("false") is False
        assert _to_bool("1") is True
        assert _to_bool("0") is False
        assert _to_bool("yes") is True
        assert _to_bool("no") is False
        with pytest.raises(ValueError):
            _to_bool("random")
        with pytest.raises(ValueError):
            _to_bool("")


class TestSecurityDefaultsEdgeCases:
    """Edge cases for security defaults."""

    def test_rabbitmq_empty_string_rejected(self):
        from unittest.mock import patch
        from services.shared.runtime.rabbitmq_http_broker import RabbitMQHTTPTopicBroker

        with patch("services.shared.runtime.rabbitmq_http_broker.load_dotenv_file"):
            with patch.dict(
                "os.environ", {"RABBITMQ_DEFAULT_USER": "", "RABBITMQ_DEFAULT_PASS": ""}
            ):
                with pytest.raises(RuntimeError, match="RABBITMQ_DEFAULT"):
                    RabbitMQHTTPTopicBroker.from_env()

    def test_database_empty_password_rejected(self):
        from unittest.mock import patch
        from services.shared.runtime.database import load_runtime_database_settings

        with patch("services.shared.runtime.database.load_dotenv_file"):
            with pytest.raises(RuntimeError, match="POSTGRES_PASSWORD"):
                load_runtime_database_settings(
                    env={
                        "DATABASE_URL": "",
                        "POSTGRES_PASSWORD": "",
                        "POSTGRES_HOST": "localhost",
                        "POSTGRES_DB": "test",
                        "POSTGRES_USER": "test",
                    }
                )
