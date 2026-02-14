from pathlib import Path


def test_core_trading_migration_exists() -> None:
    migration = Path("migrations/versions/20260214_0001_core_trading_schema.py")
    assert migration.exists()


def test_core_trading_migration_has_required_tables() -> None:
    migration = Path("migrations/versions/20260214_0001_core_trading_schema.py")
    content = migration.read_text(encoding="utf-8")
    assert "exchanges" in content
    assert "symbols" in content
    assert "orders" in content
    assert "fills" in content
    assert "positions" in content
    assert "portfolio_snapshots" in content


def test_timeseries_migration_exists() -> None:
    migration = Path("migrations/versions/20260214_0002_timeseries_schema.py")
    assert migration.exists()


def test_timeseries_migration_has_hypertables() -> None:
    migration = Path("migrations/versions/20260214_0002_timeseries_schema.py")
    content = migration.read_text(encoding="utf-8")
    assert "klines" in content
    assert "orderbook_snapshots" in content
    assert "create_hypertable" in content
