from unittest.mock import patch

import mtfck.db
from mtfck.db import get_connection
from mtfck.ingestion import create_table, process_symbol_changes


def _reset_shared_conn() -> None:
    if mtfck.db._SHARED_CONN:
        mtfck.db._SHARED_CONN.close()
        mtfck.db._SHARED_CONN = None


def test_symbol_merge_arisinfra_to_aris(tmp_path):
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

        csv_content = (
            "Company Name,Old Symbol,New Symbol,Change Date\n"
            "Aris Infra,ARISINFRA,ARIS,09-Feb-2026\n"
        )

        with patch("mtfck.ingestion._download_symbol_change_csv", return_value=csv_content):
            process_symbol_changes()

        # Old symbol should be removed
        old_count = conn.execute(
            "SELECT count(*) FROM stock_data WHERE symbol='ARISINFRA'"
        ).fetchone()[0]
        assert old_count == 0

        # New symbol should carry data
        new_row = conn.execute(
            """
            SELECT symbol, qty_financed, amt_financed
            FROM stock_data
            WHERE symbol='ARIS' AND date='2026-02-08'
            """
        ).fetchone()
        assert new_row == ("ARIS", 1000, 50000.0)

    _reset_shared_conn()
