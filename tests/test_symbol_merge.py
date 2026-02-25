import pytest
from unittest.mock import patch, MagicMock
from datetime import date
from mtfck.ingestion import create_table, process_symbol_changes
from mtfck.db import get_connection, close_connection
import mtfck.db

@pytest.fixture
def temp_db(tmp_path):
    # Use a temporary file for the database
    db_file = tmp_path / "test_stock_data.duckdb"

    # Patch DB_PATH in mtfck.db
    with patch("mtfck.db.DB_PATH", str(db_file)):
        # Reset any existing connection
        mtfck.db._SHARED_CONN = None

        # Initialize schema
        create_table()

        yield str(db_file)

        # Cleanup
        close_connection()
        mtfck.db._SHARED_CONN = None

def test_symbol_merge_arisinfra_to_aris(temp_db):
    conn = get_connection()

    # 1. Setup Initial State: Old Symbol Exists
    # Insert ARISINFRA
    conn.execute("INSERT INTO stock_master (symbol, name, industry) VALUES ('ARISINFRA', 'Aris Infra', 'Construction')")

    # Get ID
    arisinfra_id = conn.sql("SELECT stock_id FROM stock_master WHERE symbol = 'ARISINFRA'").fetchone()[0]

    # Insert some data for ARISINFRA
    test_date = date(2026, 2, 8)
    conn.execute(f"INSERT INTO stock_data (date, stock_id, qty_financed, amt_financed) VALUES ('{test_date}', {arisinfra_id}, 1000, 50000)")

    # Verify initial state
    res = conn.sql(f"SELECT count(*) FROM stock_data WHERE stock_id = {arisinfra_id}").fetchone()[0]
    assert res == 1

    # 2. Mock the CSV download
    csv_content = (
        "Company Name,Old Symbol,New Symbol,Change Date\n"
        "Aris Infra,ARISINFRA,ARIS,09-Feb-2026\n"
    ).encode('ISO-8859-1')

    mock_response = MagicMock()
    mock_response.content = csv_content
    mock_response.raise_for_status.return_value = None

    # 3. Call process_symbol_changes
    with patch("requests.get", return_value=mock_response):
        process_symbol_changes()

    # 4. Verify Results

    # ARIS should exist in stock_master
    res = conn.sql("SELECT stock_id, symbol, name, industry FROM stock_master WHERE symbol = 'ARIS'").fetchone()
    assert res is not None
    aris_id = res[0]
    assert res[1] == 'ARIS'
    assert res[2] == 'Aris Infra'
    assert res[3] == 'Construction' # Should inherit industry

    # ARISINFRA should be gone from stock_master (or at least no data points to it)
    # The current logic deletes old master record if merge/rename successful
    res = conn.sql("SELECT count(*) FROM stock_master WHERE symbol = 'ARISINFRA'").fetchone()[0]
    assert res == 0

    # Data should be moved to ARIS
    res = conn.sql(f"SELECT count(*) FROM stock_data WHERE stock_id = {aris_id}").fetchone()[0]
    assert res == 1

    # Verify data content
    data_row = conn.sql(f"SELECT qty_financed, amt_financed FROM stock_data WHERE stock_id = {aris_id}").fetchone()
    assert data_row[0] == 1000
    assert data_row[1] == 50000
