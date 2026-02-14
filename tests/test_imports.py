from mtfck.mtfck import DB_PATH
from mtfck.ingestion import create_table


def test_imports():
    """Simple test to verify modules can be imported and constants accessed."""
    assert "db/stock_data.db" in DB_PATH
    assert callable(create_table)
