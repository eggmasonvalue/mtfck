from unittest.mock import patch

import mtfck.db
from mtfck.db import get_connection
from mtfck.ingestion import create_table


def _reset_shared_conn() -> None:
    if mtfck.db._SHARED_CONN:
        mtfck.db._SHARED_CONN.close()
        mtfck.db._SHARED_CONN = None


def test_create_table_initializes_expected_tables(tmp_path):
    db_file = tmp_path / "stock_data.parquet"
    summary_file = tmp_path / "daily_summary.parquet"

    _reset_shared_conn()
    with (
        patch("mtfck.db.DB_PATH", str(db_file)),
        patch("mtfck.db.SUMMARY_PATH", str(summary_file)),
    ):
        create_table()
        conn = get_connection()

        table_names = {
            row[0]
            for row in conn.execute("SHOW TABLES").fetchall()
        }

    assert "stock_data" in table_names
    assert "daily_summary" in table_names

    _reset_shared_conn()


def test_create_table_allows_stock_data_roundtrip(tmp_path):
    db_file = tmp_path / "stock_data.parquet"
    summary_file = tmp_path / "daily_summary.parquet"

    _reset_shared_conn()
    with (
        patch("mtfck.db.DB_PATH", str(db_file)),
        patch("mtfck.db.SUMMARY_PATH", str(summary_file)),
    ):
        create_table()
        conn = get_connection(read_only=False)
        conn.execute(
            """
            INSERT INTO stock_data (date, symbol, qty_financed, amt_financed)
            VALUES ('2026-02-08', 'ARISINFRA', 1000, 50000)
            """
        )
        row = conn.execute(
            "SELECT symbol, qty_financed, amt_financed FROM stock_data WHERE date='2026-02-08'"
        ).fetchone()

    assert row == ("ARISINFRA", 1000, 50000.0)

    _reset_shared_conn()
