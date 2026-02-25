import duckdb
import os

DB_PATH = "mtf_data/stock_data.parquet"
SUMMARY_PATH = "mtf_data/daily_summary.parquet"
_SHARED_CONN = None

def get_connection(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """
    Establish and return a shared connection to an in-memory DuckDB database,
    with views pointing to the local Parquet files.
    """
    global _SHARED_CONN
    
    if _SHARED_CONN is not None:
        return _SHARED_CONN
        
    _SHARED_CONN = duckdb.connect(':memory:')
    
    # Create views if the parquet files exist
    if os.path.exists(DB_PATH):
        _SHARED_CONN.execute(f"CREATE TABLE stock_data AS SELECT * FROM read_parquet('{DB_PATH}')")
    else:
        _SHARED_CONN.execute("CREATE TABLE stock_data (date DATE, symbol VARCHAR, qty_financed INTEGER, amt_financed REAL)")
        
    if os.path.exists(SUMMARY_PATH):
        _SHARED_CONN.execute(f"CREATE TABLE daily_summary AS SELECT * FROM read_parquet('{SUMMARY_PATH}')")
    else:
        _SHARED_CONN.execute("CREATE TABLE daily_summary (date DATE, total_outstanding_begin REAL, fresh_exposure REAL, exposure_liquidated REAL, net_outstanding_end REAL)")
        
    return _SHARED_CONN

def close_connection():
    """Close the shared database connection if one exists."""
    global _SHARED_CONN
    if _SHARED_CONN:
        _SHARED_CONN.close()
        _SHARED_CONN = None
