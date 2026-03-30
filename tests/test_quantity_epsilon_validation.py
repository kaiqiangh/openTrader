"""CQ-004: Epsilon-based quantity validation consistency tests."""

from __future__ import annotations

import pytest


def test_validate_rejects_sub_epsilon_quantity():
    """Quantity below epsilon threshold should be rejected."""
    from services.api.internal_execution.adapters import validate_create_order_fields
    from services.api.internal_execution import InternalDispatchValidationError

    with pytest.raises(InternalDispatchValidationError, match="quantity must be positive"):
        validate_create_order_fields(
            order_type="MARKET",
            time_in_force=None,
            quantity=1e-10,  # below epsilon but above zero
            limit_price=None,
            trigger_price=None,
        )


def test_validate_accepts_above_epsilon_quantity():
    """Quantity above epsilon should be accepted."""
    from services.api.internal_execution.adapters import validate_create_order_fields

    # Should not raise
    validate_create_order_fields(
        order_type="MARKET",
        time_in_force=None,
        quantity=1e-8,  # above epsilon
        limit_price=None,
        trigger_price=None,
    )


def test_validate_rejects_zero_quantity():
    """Zero quantity should still be rejected."""
    from services.api.internal_execution.adapters import validate_create_order_fields
    from services.api.internal_execution import InternalDispatchValidationError

    with pytest.raises(InternalDispatchValidationError, match="quantity must be positive"):
        validate_create_order_fields(
            order_type="MARKET",
            time_in_force=None,
            quantity=0.0,
            limit_price=None,
            trigger_price=None,
        )
