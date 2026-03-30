"""Test that PortfolioSnapshot uses realized_pnl_total, not realized_pnl_total."""


def test_portfolio_snapshot_uses_total_not_today():
    """Field should be realized_pnl_total, not realized_pnl_total."""
    from services.oms.portfolio_snapshot import PortfolioSnapshot
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(PortfolioSnapshot)}
    assert "realized_pnl_total" in field_names, "Should have realized_pnl_total"
    assert "realized_pnl_today" not in field_names, "Should NOT have realized_pnl_today"
