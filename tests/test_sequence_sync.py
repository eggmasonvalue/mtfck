import pytest
from unittest.mock import patch
from mtfck.ingestion import sync_sequence, create_table
from mtfck.db import get_connection
import mtfck.db

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_seq.duckdb"

    if mtfck.db._SHARED_CONN:
        mtfck.db._SHARED_CONN.close()
        mtfck.db._SHARED_CONN = None

    with patch("mtfck.db.DB_PATH", str(db_file)):
        create_table()
        yield str(db_file)

    if mtfck.db._SHARED_CONN:
        mtfck.db._SHARED_CONN.close()
        mtfck.db._SHARED_CONN = None

def test_sync_sequence_lagging(temp_db):
    conn = get_connection()

    # Use sequence once to initialize if needed
    conn.execute("INSERT INTO stock_master (symbol, name) VALUES ('INIT', 'Init Co')")

    # Initial state: sequence at 1
    seq_val = conn.execute("SELECT last_value FROM duckdb_sequences() WHERE sequence_name='stock_id_seq'").fetchone()[0]
    assert seq_val == 1

    # Insert manually bypassing sequence (ID 10)
    conn.execute("INSERT INTO stock_master (stock_id, symbol, name) VALUES (10, 'TEST', 'Test Co')")

    # Call sync
    sync_sequence()

    # Check sequence
    seq_val = conn.execute("SELECT last_value FROM duckdb_sequences() WHERE sequence_name='stock_id_seq'").fetchone()[0]
    assert seq_val >= 10

    # Next insert using sequence should be > 10 (likely 11)
    conn.execute("INSERT INTO stock_master (symbol, name) VALUES ('NEXT', 'Next Co')")
    new_id = conn.execute("SELECT stock_id FROM stock_master WHERE symbol='NEXT'").fetchone()[0]
    assert new_id > 10

def test_sync_sequence_ok(temp_db):
    conn = get_connection()

    # Use sequence normally
    conn.execute("INSERT INTO stock_master (symbol, name) VALUES ('A', 'A Co')") # ID 1, Seq 1

    sync_sequence()

    # Seq should still be fine (1 or more)
    seq_val = conn.execute("SELECT last_value FROM duckdb_sequences() WHERE sequence_name='stock_id_seq'").fetchone()[0]
    assert seq_val >= 1

    # Next insert
    conn.execute("INSERT INTO stock_master (symbol, name) VALUES ('B', 'B Co')")
    new_id = conn.execute("SELECT stock_id FROM stock_master WHERE symbol='B'").fetchone()[0]
    assert new_id > 1
