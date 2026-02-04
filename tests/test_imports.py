from mtfck import DB_PATH
from ingestion import create_table

def test_imports():
    """Simple test to verify modules can be imported and constants accessed."""
    assert DB_PATH == "./stock_data.db"
    assert callable(create_table)
