from __future__ import annotations

import pytest


def test_requested_quantity_zero_rejected():
    """Orders with zero requested_quantity should be rejected at creation."""
    from services.workers.main import _resolve_requested_quantity

    with pytest.raises(ValueError, match="requested_quantity must be positive"):
        _resolve_requested_quantity(0.0)


def test_requested_quantity_negative_converted():
    """Negative quantity should be converted to positive via abs()."""
    from services.workers.main import _resolve_requested_quantity

    assert _resolve_requested_quantity(-1.0) == 1.0
    assert _resolve_requested_quantity(-5.5) == 5.5


def test_requested_quantity_none_rejected():
    """Orders with None/missing quantity should be rejected."""
    from services.workers.main import _resolve_requested_quantity

    with pytest.raises(ValueError, match="requested_quantity must be positive"):
        _resolve_requested_quantity(None)


def test_requested_quantity_positive_accepted():
    """Valid positive quantity should return abs value."""
    from services.workers.main import _resolve_requested_quantity

    assert _resolve_requested_quantity(1.5) == 1.5
    assert _resolve_requested_quantity(-2.0) == 2.0
